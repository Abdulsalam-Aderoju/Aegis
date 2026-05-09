# Aegis:  Disease Outbreak Forecasting System

A full-stack web application for government agencies to track and predict disease outbreaks, deployed on Azure with a complete DevOps implementation including Infrastructure as Code, CI/CD pipelines, and observability.

> This is a **Portfolio project** built to demonstrate end-to-end DevOps engineering on a real application.


Aegis is a 3-tier web application:
- **Frontend** — HTML/CSS/JavaScript interface for coordinators and federal agencies
- **Backend** — FastAPI with an integrated ML model for outbreak prediction
- **Database** — PostgreSQL storing user accounts, Nigerian state data, and outbreak records

The DevOps work in this repo covers everything required to take that application from a local machine to a production cloud environment: provisioning infrastructure, containerizing the backend, automating deployments, and monitoring the live system.

---

## Architecture

<img width="741" height="479" alt="Aegis Architecture" src="https://github.com/user-attachments/assets/f34c85d2-01be-42ed-b955-b1e49c6e18d9" />


### How the pieces connect

| Layer | Service | Why |
|---|---|---|
| Frontend | Azure Static Web Apps | Static files need no server; free tier, global CDN, auto SSL |
| Backend | Azure Container Apps | Serverless containers; scales to zero; no server management |
| Database | Azure Database for PostgreSQL | Fully managed; handles backups and patches automatically |
| Image Registry | Azure Container Registry | Private Docker registry; integrates natively with Container Apps |
| IaC | Terraform | All infrastructure defined as code; reproducible in minutes |
| CI/CD | GitHub Actions | Automated pipelines triggered by code pushes |
| Observability | Azure Monitor + Application Insights | Logs, traces and metrics in one place |

---

## Repository Structure

```
Aegis/
├── Aegis-Frontend/          # HTML/CSS/JS frontend
├── Aegis-Backend/           # FastAPI backend + Dockerfile
│   ├── app/
│   │   ├── routes/
│   │   ├── models/
│   │   ├── ml/
│   │   ├── database.py
│   │   └── config.py
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── Aegis-Terraform/         # All infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   └── terraform.tfvars     # ← NOT committed (secrets)
├── .github/
│   └── workflows/
│       ├── deploy-backend.yml
│       └── deploy-frontend.yml
└── .gitignore
```

---

## Running Locally

### Prerequisites
- Python 3.13+
- Docker Desktop
- PostgreSQL (or use Docker Compose)

### 1. Clone the repo
```bash
git clone https://github.com/Abdulsalam-Aderoju/Aegis.git
cd Aegis
```

### 2. Set up the backend
```bash
cd Aegis-Backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configure environment variables
Create a `.env` file inside `Aegis-Backend/`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:admin@localhost:5432/aegis_db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
APPINSIGHTS_CONNECTION_STRING=
```

### 4. Run with Docker Compose (recommended)
From the `Aegis-Backend/` folder:
```bash
docker-compose up
```
This spins up the backend and a local PostgreSQL database together. The backend waits for the database to be healthy before starting.

### 5. Run the frontend
Open `Aegis-Frontend/index.html` directly in your browser, or serve it with any static file server.

---

## Deploying to Azure

### Prerequisites
- [Terraform](https://developer.hashicorp.com/terraform/install) installed
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running
- An Azure account with active subscription

### 1. Authenticate with Azure
```bash
az login --use-device-code
set ARM_SUBSCRIPTION_ID=your-subscription-id
```

### 2. Configure Terraform secrets
Create `Aegis-Terraform/terraform.tfvars`:
```hcl
db_password = "YourStrongPassword123!"
```
> ⚠️ This file is in `.gitignore` and must never be committed.

### 3. Provision infrastructure
```bash
cd Aegis-Terraform
terraform init
terraform plan
terraform apply
```
This creates the resource group, PostgreSQL server, database, container registry, container app environment, container app, static web app, log analytics workspace, application insights, metric alerts, action group, availability test and dashboard — in the correct dependency order.

### 4. Push the Docker image
```bash
cd ../Aegis-Backend
az acr login --name aegislanreyacr
docker build -t aegislanreyacr.azurecr.io/aegis-backend:latest .
docker push aegislanreyacr.azurecr.io/aegis-backend:latest
```

### 5. Apply again to deploy the container app
```bash
cd ../Aegis-Terraform
terraform apply
```

### 6. Seed the database
Connect to the Azure PostgreSQL instance via TablePlus or psql:
- **Host:** `aegis-postgres-server.postgres.database.azure.com`
- **Port:** `5432`
- **Database:** `aegisdb`
- **Username:** `aegisadmin`
- **SSL:** Required

Run `seed.sql` to populate the required accounts and state data.

### 7. Get your live URLs
```bash
terraform output db_host

az containerapp show \
  --name aegis-backend \
  --resource-group rg-aegis-portfolio \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv

az staticwebapp show \
  --name aegis-frontend \
  --resource-group rg-aegis-portfolio \
  --query "defaultHostname" \
  --output tsv
```

### 8. Destroy when not in use
```bash
terraform destroy
```
PostgreSQL bills by the hour. Destroy after every session to avoid unnecessary cost and re-apply when needed. The entire environment rebuilds in under 10 minutes.

---

## CI/CD Pipelines

Both pipelines live in `.github/workflows/` and are triggered automatically on push to `main`.

### Backend pipeline (`deploy-backend.yml`)
Triggers on changes to `Aegis-Backend/**`

```
Push to main
  → Build Docker image
  → Authenticate with Azure (Service Principal)
  → Push image to ACR
  → Update Container App with new image
```

### Frontend pipeline (`deploy-frontend.yml`)
Triggers on changes to `Aegis-Frontend/**`

```
Push to main
  → Deploy static files to Azure Static Web Apps
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AZURE_CREDENTIALS` | Service Principal JSON (from `az ad sp create-for-rbac`) |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Deployment token from Static Web Apps |

---

## Observability

All three pillars of observability are implemented via Azure Monitor.

| Pillar | Tool | What it tracks |
|---|---|---|
| Logs | Azure Log Analytics | All container and database logs, queryable via KQL |
| Traces | Application Insights | Every HTTP request, response time, errors, user visits |
| Metrics | Azure Monitor Metric Alerts | CPU, memory, container restarts, DB connections |

### Metric alert thresholds

| Alert | Threshold | Action |
|---|---|---|
| CPU usage | > 80% | Email notification |
| Memory usage | > 80% | Email notification |
| Container restarts | > 3 | Email notification |
| DB active connections | > 50 | Email notification |

### Availability test
A synthetic ping test runs every 5 minutes from 3 geographic locations, tracking uptime percentage over time.

---

## Key Decisions

**Why Azure Container Apps over a VM?**
A VM requires managing the OS, security patches, runtime and scaling. Container Apps abstracts all of that, I simply provide a Docker image and Azure handles the rest. It also scales to zero, meaning I pay nothing when there's no traffic.

**Why Docker?**
The application runs identically whether it's on my Windows laptop, in CI/CD, or in Azure. It eliminates environment inconsistency between development and production.

**Why Terraform over clicking in the Azure portal?**
The portal is fine for exploration but produces infrastructure that can't be reproduced reliably. Terraform gives version control, repeatability, and the ability to destroy and recreate the entire environment from scratch in minutes which is essential when managing cost on a personal project.

**Why separate CI/CD pipelines for frontend and backend?**
A frontend change shouldn't trigger a backend Docker build and redeployment. Path-based triggers mean each component (Frontend and Backend) deploys independently.

**Why Azure Monitor over Prometheus and Grafana?**
Prometheus and Grafana are the standard stack for self-managed Kubernetes environments where you need to scrape metrics yourself. On Azure's managed services like the one we used in this project, Azure Monitor receives metrics natively and there's nothing to scrape. Adding Prometheus on top would be redundant complexity.

---

## What I Would Improve

| Improvement | Why it matters |
|---|---|
| Modular Terraform | One large `main.tf` becomes hard to maintain; modules make infrastructure reusable |
| Remote Terraform state | Local state file breaks team workflows; Azure Blob Storage enables collaboration and state locking |
| Private VNet for PostgreSQL | Database is currently accessible over the internet; a VNet restricts it to internal traffic only |
| Azure Key Vault for secrets | `terraform.tfvars` is a basic approach; Key Vault is the production standard |
| Staging environment | No staging means changes go directly to production; a dev → staging → prod pipeline adds safety |
| Automated tests in CI/CD | The pipeline deploys without running any tests first |
| Frontend Application Insights | Traces currently only cover the backend; adding the JS SDK completes the full end-to-end picture (Real User Monitoring) |

---

## Tech Stack

**Application**
- FastAPI · SQLAlchemy (async) · asyncpg · Pydantic · JWT auth · JAX · scikit-learn

**DevOps**
- Terraform · Docker · GitHub Actions · Azure CLI

**Azure Services**
- Container Apps · Container Registry · Static Web Apps · Database for PostgreSQL · Monitor · Application Insights · Log Analytics · Key Vault

---

## Related

- 📝 [Read the full article on Substack](https://substack.com/@aderojuabdulsalamolanrewaju/note/p-196304215?utm_source=notes-share-action&r=fcolv) — walkthrough of every decision made in this project
- 🔗 [Live frontend](https://kind-bush-0ccea460f.7.azurestaticapps.net/)

---

*Built by [Abdulsalam Aderoju](https://www.linkedin.com/in/abdulsalam-aderoju/)*
