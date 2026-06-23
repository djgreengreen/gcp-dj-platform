# GCP DJ Platform — Cloud Storage (MP3 Dropzone)
# Replaces local /root/XtremeTags/dropzone

resource "google_storage_bucket" "dropzone" {
  name          = "${var.project_id}-${var.bucket_name}"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = true # Easy teardown for learning project

  # Auto-delete files older than 30 days to keep costs down
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  # Optional: move to NEARLINE after 7 days if not accessed
  lifecycle_rule {
    condition {
      age                   = 7
      matches_storage_class = ["STANDARD"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_project_service.apis]
}

# IAM: allow Cloud Run processor to read objects
resource "google_storage_bucket_iam_member" "processor_read" {
  bucket = google_storage_bucket.dropzone.name
  role   = "roles/storage.objectAdmin"  # read + delete after processing
  member = "serviceAccount:${google_service_account.processor.email}"
}

output "dropzone_bucket" {
  value = google_storage_bucket.dropzone.name
}

output "dropzone_url" {
  value = "gs://${google_storage_bucket.dropzone.name}"
}

# ── Output bucket (processed/retagged MP3s) ────────────────────────
resource "google_storage_bucket" "output" {
  name          = "${var.project_id}-dj-funk-output"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = true

  # Keep processed files for 90 days, then archive
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "processor_write_output" {
  bucket = google_storage_bucket.output.name
  role   = "roles/storage.objectAdmin"  # rewrite needs get+create+delete
  member = "serviceAccount:${google_service_account.processor.email}"
}

output "output_bucket" {
  value = google_storage_bucket.output.name
}

output "output_bucket_url" {
  value = "gs://${google_storage_bucket.output.name}"
}
