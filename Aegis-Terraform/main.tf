terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}


resource "azurerm_resource_group" "aegis_rg" {
  name     = "rg-aegis-portfolio"
  location = "South Africa North"
}

resource "azurerm_postgresql_flexible_server" "aegis_db" {
  name                   = "aegis-postgres-server"
  resource_group_name    = azurerm_resource_group.aegis_rg.name
  location               = azurerm_resource_group.aegis_rg.location
  version                = "16"
  administrator_login    = "aegisadmin"
  administrator_password = var.db_password
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"
  zone                   = "1"
}

resource "azurerm_postgresql_flexible_server_database" "aegis_database" {
  name      = "aegisdb"
  server_id = azurerm_postgresql_flexible_server.aegis_db.id
}


resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.aegis_db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}


resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_local" {
  name             = "allow-local-machine"
  server_id        = azurerm_postgresql_flexible_server.aegis_db.id
  start_ip_address = "102.88.110.156"
  end_ip_address   = "102.88.110.156"
}


# Where Docker Image is stored
resource "azurerm_container_registry" "aegis_acr" {
  name                = "aegislanreyacr"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  location            = azurerm_resource_group.aegis_rg.location
  sku                 = "Basic"
  admin_enabled       = true
}


# Container Apps Environment
resource "azurerm_container_app_environment" "aegis_env" {
  name                = "aegis-container-env"
  location            = azurerm_resource_group.aegis_rg.location
  resource_group_name = azurerm_resource_group.aegis_rg.name
}


# Container App (Backend)
resource "azurerm_container_app" "aegis_backend" {
  name                         = "aegis-backend"
  container_app_environment_id = azurerm_container_app_environment.aegis_env.id
  resource_group_name          = azurerm_resource_group.aegis_rg.name
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.aegis_acr.login_server
    username             = azurerm_container_registry.aegis_acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.aegis_acr.admin_password
  }

  template {
    container {
      name   = "aegis-backend"
      image  = "${azurerm_container_registry.aegis_acr.login_server}/aegis-backend:latest"
      cpu    = 1
      memory = "2Gi"

      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://aegisadmin:${var.db_password}@${azurerm_postgresql_flexible_server.aegis_db.fqdn}/aegisdb?ssl=require"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}


# Static Web App (Frontend)
resource "azurerm_static_web_app" "aegis_frontend" {
  name                = "aegis-frontend"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  location            = "East US 2"
  sku_tier            = "Free"
  sku_size            = "Free"
}


output "db_host" {
  value = azurerm_postgresql_flexible_server.aegis_db.fqdn
}