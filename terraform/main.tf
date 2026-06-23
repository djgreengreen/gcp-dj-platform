# GCP DJ Platform — Main Terraform Config
# Project: xtremetag-1984
# Region:  australia-southeast1 (Sydney)

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # Use local state for now — migrate to GCS backend later if needed
}

provider "google" {
  project         = var.project_id
  region          = var.region
  billing_project = var.project_id
}

# ── Enable required APIs ──────────────────────────────────────────
locals {
  required_apis = [
    "cloudresourcemanager.googleapis.com", # Project management
    "serviceusage.googleapis.com",         # API enablement
    "storage.googleapis.com",              # GCS
    "pubsub.googleapis.com",               # Pub/Sub
    "run.googleapis.com",                  # Cloud Run
    "artifactregistry.googleapis.com",     # Container registry
    "bigquery.googleapis.com",             # BigQuery
    "bigqueryconnection.googleapis.com",   # BigQuery connections
    "secretmanager.googleapis.com",        # Secret Manager
    "cloudbuild.googleapis.com",           # Cloud Build (container builds)
    "cloudbilling.googleapis.com",         # Budget alerts
    "monitoring.googleapis.com",           # Monitoring
    "iamcredentials.googleapis.com",       # Service account auth
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ── Service Account for Cloud Run processor ────────────────────────
resource "google_service_account" "processor" {
  account_id   = "dj-processor"
  display_name = "DJ Music Processor (Cloud Run)"
  depends_on   = [google_project_service.apis]
}

# ── Link billing account to project ────────────────────────────────
resource "google_billing_project_info" "default" {
  billing_account = var.billing_account
  project         = var.project_id
  depends_on      = [google_project_service.apis]
}

# ── Outputs ────────────────────────────────────────────────────────
output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "processor_service_account" {
  value = google_service_account.processor.email
}
