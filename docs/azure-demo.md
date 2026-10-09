# Part 2: Azure with Terraform

Status: deployable infrastructure configuration; actual subscription apply is pending.
Scope: the Python inference/evaluation platform (AKS, ACR, CPU/GPU pools, persistent reports,
vLLM and manual evaluation job; result API in Part 3). This does not migrate the separate Java
application, MySQL, Redis or its provider credentials. Those existing Java evaluation commands remain local.

## Prerequisites

Azure CLI authenticated with `az login`, Terraform >=1.9, kubectl, and permission to create role
assignments. Check regional quota for the selected NVIDIA VM size first. Both CPU pools, registry,
storage and networking incur charges even with `gpu_enabled=false`. Set a budget in Azure.
GPU inference requires a Linux NVIDIA node; a local Apple GPU is not compatible with this manifest.

Use two Terraform roots: the cluster must exist before the Kubernetes provider can plan workloads.
Local state is for a single-person demo; keep it private and move to an Azure Storage remote backend
before collaborating. Do not commit state, plans, credentials or tfvars.

```bash
cp infra/azure/terraform.tfvars.example infra/azure/terraform.tfvars
# Fill subscription, globally unique lowercase registry name, and your public IP/32.
terraform -chdir=infra/azure init
terraform -chdir=infra/azure plan -out=demo.tfplan
terraform -chdir=infra/azure apply demo.tfplan
az aks get-credentials --resource-group llmeval-rg --name llmeval-aks
```

Confirm the context printed by `kubectl config current-context`; use it explicitly below.
Build on Azure ACR so an Apple workstation still produces a Linux/amd64 image:

```bash
# Replace YOUR_ACR with terraform output registry_name.
az acr build --registry YOUR_ACR --image llm-eval:demo-v1 --platform linux/amd64 .
terraform -chdir=infra/workloads init
terraform -chdir=infra/workloads plan \
  -var='kube_context=llmeval-aks' \
  -var='eval_image=YOUR_ACR.azurecr.io/llm-eval:demo-v1' -out=demo.tfplan
terraform -chdir=infra/workloads apply demo.tfplan
```

CPU-only installation can query existing reports after Part 3, but inference jobs require the GPU pool.
For inference: change `gpu_enabled=true` in the Azure tfvars, plan and apply the first root.
Then plan and apply workloads with **the same `-var` values plus `-var='gpu_enabled=true'`**.
This installs the NVIDIA device plugin on the standard Ubuntu GPU pool. Do not install a second
plugin if using a managed GPU pool/operator instead. Verify `nvidia.com/gpu` allocatable before starting.

```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu
kubectl -n llm-eval rollout status deployment/vllm --timeout=1200s
kubectl -n llm-eval create job --from=cronjob/eval-benchmark eval-demo-001
kubectl -n llm-eval logs -f job/eval-demo-001
```

The CronJob is suspended: manual jobs are deliberate, with no unexpected scheduled GPU evaluations.
Reports persist on an Azure Files RWX volume, shared with the Part 3 API. Workload resources are
Terraform-owned; do not also apply the standalone Part 1 namespace/vLLM manifests to this same cluster.
The vLLM and result APIs use ClusterIP. Access through port-forward for the demo; no public unauthenticated endpoint.

## Record

Show the Terraform plan, AKS pools, NVIDIA resource, vLLM Ready, then an evaluation Job completing
and writing reports. A plan alone demonstrates infrastructure configuration, not a completed cloud deployment.

## Tear down after exporting reports

Destroy workloads first, passing the same variables used for apply, then destroy Azure infrastructure.
Destroy removes reports/volumes and the cluster; download any evidence first.

```bash
terraform -chdir=infra/workloads destroy \
  -var='kube_context=llmeval-aks' -var='eval_image=YOUR_ACR.azurecr.io/llm-eval:demo-v1' \
  -var='gpu_enabled=true'
terraform -chdir=infra/azure destroy
```

References: [AKS GPU support](https://learn.microsoft.com/azure/aks/gpu-cluster),
[Terraform Kubernetes planning](https://developer.hashicorp.com/terraform/tutorials/kubernetes/kubernetes-provider).
