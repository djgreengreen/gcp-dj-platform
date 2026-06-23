# GCP DJ Platform — Cloud Run (MP3 Processor)
# Equivalent of XtremeTags watchtower, running serverless on GCP

locals {
  spotify_configured = var.spotify_client_id != ""
}

# Artifact Registry for container images
resource "google_artifact_registry_repository" "processor" {
  location      = var.region
  repository_id = "dj-processor"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ── Spotify Secrets (only if credentials provided) ─────────────────

resource "google_secret_manager_secret" "spotify_client_id" {
  count     = local.spotify_configured ? 1 : 0
  secret_id = "spotify-client-id"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "spotify_client_id" {
  count       = local.spotify_configured ? 1 : 0
  secret      = google_secret_manager_secret.spotify_client_id[0].id
  secret_data = var.spotify_client_id
}

resource "google_secret_manager_secret" "spotify_client_secret" {
  count     = local.spotify_configured ? 1 : 0
  secret_id = "spotify-client-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "spotify_client_secret" {
  count       = local.spotify_configured ? 1 : 0
  secret      = google_secret_manager_secret.spotify_client_secret[0].id
  secret_data = var.spotify_client_secret
}

# Grant Cloud Run SA access to secrets (only if secrets exist)
resource "google_secret_manager_secret_iam_member" "processor_spotify_id" {
  count     = local.spotify_configured ? 1 : 0
  secret_id = google_secret_manager_secret.spotify_client_id[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_secret_manager_secret_iam_member" "processor_spotify_secret" {
  count     = local.spotify_configured ? 1 : 0
  secret_id = google_secret_manager_secret.spotify_client_secret[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}

# ── Cloud Run service ──────────────────────────────────────────────

resource "google_cloud_run_v2_service" "processor" {
  name                = "dj-processor"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account       = google_service_account.processor.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

    containers {
      # Placeholder image — replaced after building processor container
      image = "us-docker.pkg.dev/cloudrun/container/hello:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "BQ_DATASET"
        value = google_bigquery_dataset.dj.dataset_id
      }
      env {
        name  = "OUTPUT_BUCKET"
        value = google_storage_bucket.output.name
      }

      # Only inject Spotify env vars if secrets exist
      dynamic "env" {
        for_each = local.spotify_configured ? [1] : []
        content {
          name = "SPOTIFY_CLIENT_ID"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.spotify_client_id[0].secret_id
              version = "latest"
            }
          }
        }
      }
      dynamic "env" {
        for_each = local.spotify_configured ? [1] : []
        content {
          name = "SPOTIFY_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.spotify_client_secret[0].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 9
        period_seconds        = 10
        failure_threshold     = 3
        tcp_socket {
          port = 8080
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    max_instance_request_concurrency = 1
  }

  depends_on = [
    google_project_service.apis,
    google_bigquery_dataset.dj,
  ]
}

# Allow Pub/Sub to invoke Cloud Run
resource "google_cloud_run_service_iam_member" "pubsub_invoke" {
  location = google_cloud_run_v2_service.processor.location
  service  = google_cloud_run_v2_service.processor.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.processor.email}"
}

# Grant processor BigQuery write access
resource "google_bigquery_dataset_iam_member" "processor_write" {
  dataset_id = google_bigquery_dataset.dj.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.processor.email}"
}

output "cloud_run_url" {
  value = google_cloud_run_v2_service.processor.uri
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.processor.repository_id}"
}
