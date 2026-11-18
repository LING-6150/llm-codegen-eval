terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
    helm       = { source = "hashicorp/helm", version = "~> 2.17" }
  }
}
variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/config"
}
variable "kube_context" { type = string }
variable "eval_image" {
  type = string
  validation {
    condition     = can(regex("^[^ ]+:[^ ]+$|^[^ ]+@sha256:[a-f0-9]{64}$", var.eval_image)) && !endswith(var.eval_image, ":latest")
    error_message = "Provide a tagged image or digest from your registry; do not use latest."
  }
}
variable "gpu_enabled" {
  type    = bool
  default = false
}
provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}
provider "helm" {
  kubernetes {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = var.kube_context
  }
}
resource "kubernetes_namespace_v1" "eval" {
  metadata { name = "llm-eval" }
}
# Standard AKS Ubuntu GPU nodes have drivers; this chart advertises GPUs to K8s.
# Do not install this if using a managed GPU node pool/operator that owns the plugin.
resource "helm_release" "nvidia" {
  count      = var.gpu_enabled ? 1 : 0
  name       = "nvidia-device-plugin"
  repository = "https://nvidia.github.io/k8s-device-plugin"
  chart      = "nvidia-device-plugin"
  version    = "0.17.1"
  namespace  = "kube-system"
  values     = [yamlencode({ nodeSelector = { workload = "inference" } })]
}
locals {
  # VLLM contains a Deployment and a Service. CPU demo can skip both.
  vllm_documents   = var.gpu_enabled ? split("\n---\n", trimspace(file("${path.module}/../../deploy/k8s/vllm.yaml"))) : []
  common_documents = split("\n---\n", trimspace(templatefile("${path.module}/../../deploy/k8s/eval.yaml.tftpl", { eval_image = var.eval_image })))
  manifests = { for doc in concat(local.vllm_documents, local.common_documents) :
    "${yamldecode(doc).kind}-${yamldecode(doc).metadata.name}" => merge(yamldecode(doc), {
      metadata = merge(yamldecode(doc).metadata, { namespace = "llm-eval" })
  }) }
}
resource "kubernetes_manifest" "platform" {
  for_each   = local.manifests
  manifest   = each.value
  depends_on = [kubernetes_namespace_v1.eval, helm_release.nvidia]
}
