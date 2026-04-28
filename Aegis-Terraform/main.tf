terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
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



resource "azurerm_container_registry" "aegis_acr" {
  name                = "aegislanreyacr"
  resource_group_name = azurerm_resource_group.aegis_rg.name
  location            = azurerm_resource_group.aegis_rg.location
  sku                 = "Basic"
  admin_enabled       = true
}

