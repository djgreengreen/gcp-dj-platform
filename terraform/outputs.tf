# GCP DJ Platform — Terraform Outputs
# All useful values printed after terraform apply

output "gcs_dropzone_url" {
  description = "Upload MP3s here"
  value       = "gs://${google_storage_bucket.dropzone.name}"
}

output "gcs_upload_command" {
  description = "Example upload command"
  value       = "gsutil cp your-track.mp3 gs://${google_storage_bucket.dropzone.name}/"
}

output "pubsub_topic" {
  description = "Pub/Sub topic for file uploads"
  value       = google_pubsub_topic.new_track.name
}

output "cloud_run_service_url" {
  description = "Cloud Run processor endpoint"
  value       = google_cloud_run_v2_service.processor.uri
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset for queries"
  value       = "${var.project_id}.${google_bigquery_dataset.dj.dataset_id}"
}

output "bigquery_tracks_table" {
  description = "Full tracks table ID"
  value       = "${var.project_id}.${google_bigquery_dataset.dj.dataset_id}.tracks"
}

output "artifact_registry_repo" {
  description = "Docker image push target"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.processor.repository_id}"
}

output "next_steps" {
  description = "Post-deploy commands"
  value       = <<-EOT
    1. Build & push processor:
       cd processor/
       gcloud builds submit --tag ${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.processor.repository_id}/dj-processor:latest

    2. Test upload:
       gsutil cp test-track.mp3 gs://${google_storage_bucket.dropzone.name}/

    3. Query in BigQuery:
       bq query --use_legacy_sql=false "SELECT title, artist, genre, bpm, key FROM \`${var.project_id}.dj_funk.tracks\` ORDER BY ingested_at DESC LIMIT 10"

    4. AI enrichment (run after first tracks load):
       bq query --use_legacy_sql=false "SELECT AI.CLASSIFY(genre, ['Deep House', 'Tech House', 'Techno', 'Progressive', 'Trance', 'Drum and Bass', 'Hip Hop', 'Pop']) AS ai_genre FROM \`${var.project_id}.dj_funk.tracks\`"
  EOT
}
