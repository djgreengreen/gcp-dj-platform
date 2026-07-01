# GCP DJ Platform — Dataform Transformation Layer
# Note: google_dataform_repository resources are not yet available in
# the google provider v6.50. Created via REST API instead.
# Monitor: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/dataform_repository
#
# Created manually:
#   Repository: dj-funk-transforms (australia-southeast1)
#   Workspace:  production
#   Console:    https://console.cloud.google.com/dataform/locations/australia-southeast1/repositories/dj-funk-transforms?project=xtremetag-1984

# ── Grant the processor SA Dataform execution access ─────────────────
resource "google_project_iam_member" "sa_dataform_executor" {
  project = var.project_id
  role    = "roles/dataform.editor"
  member  = "serviceAccount:${google_service_account.processor.email}"
}
