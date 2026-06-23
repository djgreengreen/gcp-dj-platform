# GCP DJ Platform — BigQuery Analytics Warehouse

resource "google_bigquery_dataset" "dj" {
  dataset_id    = "dj_funk"
  friendly_name = "DJ Music Analytics"
  description   = "Track metadata, tags, audio features, and play events"
  location      = var.region
  depends_on    = [google_project_service.apis]

  # Auto-expire tables after 60 days of no updates (keep costs low)
  default_table_expiration_ms = 5184000000 # 60 days
}

# ── Tracks table ───────────────────────────────────────────────────
resource "google_bigquery_table" "tracks" {
  dataset_id          = google_bigquery_dataset.dj.dataset_id
  table_id            = "tracks"
  deletion_protection = false

  schema = jsonencode([
    { name = "track_id",      type = "STRING",  mode = "REQUIRED", description = "SHA256 hash of file path" },
    { name = "file_path",     type = "STRING",  mode = "NULLABLE", description = "Original GCS object path" },
    { name = "file_size_mb",  type = "FLOAT64", mode = "NULLABLE", description = "File size in MB" },
    { name = "content_hash",  type = "STRING",  mode = "NULLABLE", description = "SHA256 of first 1MB (content dedup)" },
    { name = "title",         type = "STRING",  mode = "NULLABLE", description = "Track title" },
    { name = "artist", type = "STRING", mode = "NULLABLE", description = "Primary artist" },
    { name = "album", type = "STRING", mode = "NULLABLE", description = "Album name" },
    { name = "genre", type = "STRING", mode = "NULLABLE", description = "Genre (from tags or Spotify)" },
    { name = "bpm", type = "FLOAT64", mode = "NULLABLE", description = "Beats per minute" },
    { name = "key", type = "STRING", mode = "NULLABLE", description = "Musical key (e.g. Am, F#m)" },
    { name = "key_camelot", type = "STRING", mode = "NULLABLE", description = "Camelot notation (e.g. 8A)" },
    { name = "duration_sec", type = "FLOAT64", mode = "NULLABLE", description = "Duration in seconds" },
    { name = "bitrate_kbps", type = "INTEGER", mode = "NULLABLE", description = "Audio bitrate" },
    { name = "sample_rate_hz", type = "INTEGER", mode = "NULLABLE", description = "Sample rate" },
    { name = "spotify_id", type = "STRING", mode = "NULLABLE", description = "Spotify track ID" },
    { name = "spotify_popularity", type = "INTEGER", mode = "NULLABLE" },
    { name = "spotify_danceability", type = "FLOAT64", mode = "NULLABLE" },
    { name = "spotify_energy", type = "FLOAT64", mode = "NULLABLE", description = "Spotify energy (0-1)" },
    { name = "spotify_valence", type = "FLOAT64", mode = "NULLABLE", description = "Spotify valence/mood (0-1)" },
    { name = "spotify_acousticness", type = "FLOAT64", mode = "NULLABLE" },
    { name = "spotify_instrumentalness", type = "FLOAT64", mode = "NULLABLE" },
    { name = "ai_mood",       type = "STRING",  mode = "NULLABLE", description = "AI-classified mood (via Vertex AI)" },
    { name = "ai_energy_label", type = "STRING", mode = "NULLABLE", description = "AI energy classification" },
    { name = "gemini_genre",  type = "STRING",  mode = "NULLABLE", description = "Genre from Gemini audio analysis" },
    { name = "gemini_genre_confidence", type = "FLOAT64", mode = "NULLABLE", description = "Gemini genre confidence (0-1)" },
    { name = "energy_level",  type = "INTEGER", mode = "NULLABLE", description = "Energy level 1-10 (from Mixed In Key comment tag)" },
    { name = "comment",       type = "STRING",  mode = "NULLABLE", description = "Raw comment from ID3 COMM/TXXX tags" },
    { name = "tags",          type = "STRING",  mode = "REPEATED", description = "Freeform tags from file metadata" },
    { name = "ingested_at", type = "TIMESTAMP", mode = "NULLABLE", description = "When row was created" },
    { name = "processed_at", type = "TIMESTAMP", mode = "NULLABLE", description = "When Cloud Run finished processing" },
  ])

  # Partition by ingestion date for efficient querying
  time_partitioning {
    type  = "DAY"
    field = "ingested_at"
  }

  # Cluster by genre + key for common query patterns
  clustering = ["genre", "key"]

  depends_on = [google_bigquery_dataset.dj]
}

# ── Processing log table ──────────────────────────────────────────
resource "google_bigquery_table" "processing_log" {
  dataset_id          = google_bigquery_dataset.dj.dataset_id
  table_id            = "processing_log"
  deletion_protection = false

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Pub/Sub message ID" },
    { name = "file_path", type = "STRING", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "REQUIRED", description = "success / error / skipped" },
    { name = "error_message", type = "STRING", mode = "NULLABLE" },
    { name = "duration_ms", type = "INTEGER", mode = "NULLABLE" },
    { name = "timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
  ])

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  depends_on = [google_bigquery_dataset.dj]
}

# ── AI Classification UDF (uses BigQuery AI.CLASSIFY) ─────────────
# This is defined as a SQL DDL — we create it post-Terraform via bq CLI
# because Terraform doesn't support CREATE FUNCTION natively for AI functions.
# See processor/main.py for post-deploy setup.

output "bigquery_dataset" {
  value = "${var.project_id}.${google_bigquery_dataset.dj.dataset_id}"
}

output "tracks_table" {
  value = "${var.project_id}.${google_bigquery_dataset.dj.dataset_id}.tracks"
}
