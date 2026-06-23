# GCP DJ Platform — Terraform Variables
# Set these in terraform.tfvars or via TF_VAR_ env vars

variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "xtremetag-1984"
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "australia-southeast1"
}

variable "billing_account" {
  description = "Billing account ID (from gcloud billing accounts list)"
  type        = string
  sensitive   = true
  # No default — must be set via TF_VAR_billing_account or terraform.tfvars
}

variable "bucket_name" {
  description = "GCS bucket name for MP3 dropzone"
  type        = string
  default     = "dj-funk-dropzone"
}

variable "budget_amount" {
  description = "Monthly budget alert threshold (USD)"
  type        = number
  default     = 5
}

variable "budget_alert_emails" {
  description = "Emails for budget alerts"
  type        = list(string)
  default     = [] # Add your email in terraform.tfvars
}

variable "spotify_client_id" {
  description = "Spotify API client ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "spotify_client_secret" {
  description = "Spotify API client secret"
  type        = string
  sensitive   = true
  default     = ""
}
