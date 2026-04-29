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

      env {
        name  = "APPINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.aegis_insights.connection_string
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





# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "aegis_logs" {
  name                = "aegis-log-analytics"
  location            = azurerm_resource_group.aegis_rg.location
  resource_group_name = azurerm_resource_group.aegis_rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

# Action Group (email alerts)
resource "azurerm_monitor_action_group" "aegis_alerts" {
  name                = "aegis-action-group"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  short_name          = "aegis"

  email_receiver {
    name          = "admin"
    email_address = "aderojuabdulsalam15@gmail.com"
  }
}

# Alert - Container App failures
resource "azurerm_monitor_metric_alert" "backend_failures" {
  name                = "aegis-backend-failures"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  scopes              = [azurerm_container_app.aegis_backend.id]
  description         = "Alert when backend has restart failures"
  severity            = 2

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.aegis_alerts.id
  }
}


# Application Insights
resource "azurerm_application_insights" "aegis_insights" {
  name                = "aegis-app-insights"
  location            = azurerm_resource_group.aegis_rg.location
  resource_group_name = azurerm_resource_group.aegis_rg.name
  workspace_id        = azurerm_log_analytics_workspace.aegis_logs.id
  application_type    = "web"
}

# CPU Alert
resource "azurerm_monitor_metric_alert" "backend_cpu" {
  name                = "aegis-backend-cpu"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  scopes              = [azurerm_container_app.aegis_backend.id]
  description         = "Alert when CPU exceeds 80%"
  severity            = 2

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "UsageNanoCores"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 800000000
  }

  action {
    action_group_id = azurerm_monitor_action_group.aegis_alerts.id
  }
}

# Memory Alert
resource "azurerm_monitor_metric_alert" "backend_memory" {
  name                = "aegis-backend-memory"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  scopes              = [azurerm_container_app.aegis_backend.id]
  description         = "Alert when memory exceeds 80%"
  severity            = 2

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "WorkingSetBytes"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 1717986918
  }

  action {
    action_group_id = azurerm_monitor_action_group.aegis_alerts.id
  }
}

# PostgreSQL Connection Alert
resource "azurerm_monitor_metric_alert" "db_connections" {
  name                = "aegis-db-connections"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  scopes              = [azurerm_postgresql_flexible_server.aegis_db.id]
  description         = "Alert when DB connections are too high"
  severity            = 2

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "active_connections"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 50
  }

  action {
    action_group_id = azurerm_monitor_action_group.aegis_alerts.id
  }
}

# Azure Dashboard
resource "azurerm_portal_dashboard" "aegis_dashboard" {
  name                = "aegis-dashboard"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  location            = azurerm_resource_group.aegis_rg.location
  dashboard_properties = jsonencode({
    lenses = {
      "0" = {
        order = 0
        parts = {
          "0" = {
            position = {
              x        = 0
              y        = 0
              rowSpan  = 4
              colSpan  = 6
            }
            metadata = {
              type = "Extension/Microsoft_Azure_Monitoring/PartType/MetricsChartPart"
              inputs = []
            }
          }
        }
      }
    }
  })
}

# Output Application Insights connection string
output "app_insights_connection_string" {
  value     = azurerm_application_insights.aegis_insights.connection_string
  sensitive = true
}







output "db_host" {
  value = azurerm_postgresql_flexible_server.aegis_db.fqdn
}