# GCP DJ Platform — Pub/Sub (File Upload Events)

# Topic for new MP3 uploads
resource "google_pubsub_topic" "new_track" {
  name       = "new-track-uploaded"
  depends_on = [google_project_service.apis]
}

# GCS notification → Pub/Sub on object finalize
# Grant GCS service account permission to publish to the topic
data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

resource "google_pubsub_topic_iam_member" "gcs_publisher" {
  topic  = google_pubsub_topic.new_track.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

resource "google_storage_notification" "new_track" {
  bucket         = google_storage_bucket.dropzone.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.new_track.id
  event_types    = ["OBJECT_FINALIZE"]
  depends_on     = [google_pubsub_topic.new_track]
}

# Dead letter topic for failed messages
resource "google_pubsub_topic" "dead_letter" {
  name       = "dead-letter"
  depends_on = [google_project_service.apis]
}

# Push subscription → Cloud Run
# Uses the Cloud Run URL directly (available after Cloud Run is created)
resource "google_pubsub_subscription" "processor" {
  name  = "processor-subscription"
  topic = google_pubsub_topic.new_track.id

  ack_deadline_seconds = 600

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.processor.uri}/"
    oidc_token {
      service_account_email = google_service_account.processor.email
    }
  }

  message_retention_duration = "604800s"

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  depends_on = [
    google_cloud_run_v2_service.processor,
    google_pubsub_topic.new_track,
  ]
}

output "new_track_topic" {
  value = google_pubsub_topic.new_track.name
}

output "processor_subscription" {
  value = google_pubsub_subscription.processor.name
}
