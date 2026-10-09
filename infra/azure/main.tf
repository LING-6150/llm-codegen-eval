terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.62" }
  }
}
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
variable "subscription_id" { type = string }
variable "location" {
  type    = string
  default = "eastus"
}
variable "prefix" {
  type    = string
  default = "llmeval"
  validation {
    condition     = can(regex("^[a-z][a-z0-9]{3,15}$", var.prefix))
    error_message = "Use 4-16 lowercase alphanumeric characters starting with a letter."
  }
}
variable "registry_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9]{5,50}$", var.registry_name))
    error_message = "Use a globally unique 5-50 character alphanumeric ACR name."
  }
}
variable "gpu_vm_size" {
  type    = string
  default = "Standard_NC4as_T4_v3"
}
variable "gpu_enabled" {
  type    = bool
  default = false
}
variable "api_authorized_ip_ranges" {
  type = list(string)
  validation {
    condition     = length(var.api_authorized_ip_ranges) > 0 && alltrue([for cidr in var.api_authorized_ip_ranges : can(cidrhost(cidr, 0)) && cidr != "0.0.0.0/0"])
    error_message = "Provide the CIDR of your deployment machine, e.g. 203.0.113.10/32; do not use 0.0.0.0/0."
  }
}
resource "azurerm_resource_group" "eval" {
  name     = "${var.prefix}-rg"
  location = var.location
  tags     = { project = "llm-codegen-eval", environment = "demo" }
}
resource "azurerm_container_registry" "eval" {
  name                = var.registry_name
  resource_group_name = azurerm_resource_group.eval.name
  location            = var.location
  sku                 = "Basic"
  admin_enabled       = false
}
resource "azurerm_kubernetes_cluster" "eval" {
  name                              = "${var.prefix}-aks"
  location                          = var.location
  resource_group_name               = azurerm_resource_group.eval.name
  dns_prefix                        = var.prefix
  sku_tier                          = "Free"
  role_based_access_control_enabled = true
  default_node_pool {
    name                         = "system"
    node_count                   = 1
    vm_size                      = "Standard_D2s_v5"
    only_critical_addons_enabled = true
    temporary_name_for_rotation  = "systmp"
  }
  identity { type = "SystemAssigned" }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "azure"
    load_balancer_sku   = "standard"
  }
  api_server_access_profile {
    authorized_ip_ranges = var.api_authorized_ip_ranges
  }
}
# CPU user pool for evaluation jobs and result API, separate from system add-ons.
resource "azurerm_kubernetes_cluster_node_pool" "cpu" {
  name                  = "workers"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.eval.id
  vm_size               = "Standard_D2s_v5"
  node_count            = 1
  mode                  = "User"
  os_sku                = "Ubuntu"
}
resource "azurerm_kubernetes_cluster_node_pool" "gpu" {
  count                 = var.gpu_enabled ? 1 : 0
  name                  = "gpu"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.eval.id
  vm_size               = var.gpu_vm_size
  node_count            = 1
  mode                  = "User"
  os_sku                = "Ubuntu"
  node_taints           = ["nvidia.com/gpu=present:NoSchedule"]
  node_labels           = { workload = "inference" }
}
resource "azurerm_role_assignment" "pull" {
  scope                            = azurerm_container_registry.eval.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.eval.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}
output "resource_group" { value = azurerm_resource_group.eval.name }
output "cluster_name" { value = azurerm_kubernetes_cluster.eval.name }
output "registry_login_server" { value = azurerm_container_registry.eval.login_server }
output "registry_name" { value = azurerm_container_registry.eval.name }
