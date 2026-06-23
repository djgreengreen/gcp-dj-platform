# GCP DJ Music Platform

Serverless event-driven pipeline for DJ music library management on Google Cloud Platform. Drop MP3s into a GCS bucket — metadata is extracted, Gemini AI classifies the genre, and everything lands in BigQuery with a live Looker-style dashboard.

## Architecture

```
┌──────────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────┐     ┌────────────┐
│  GCS Bucket  │────▶│ Pub/Sub  │────▶│  Cloud Run   │────▶│ BigQuery  │────▶│  Looker    │
│  (dropzone)  │     │ (events) │     │ (processor)  │     │(warehouse)│     │ Dashboard  │
└──────┬───────┘     └──────────┘     └──────┬───────┘     └─────┬────┘     └────────────┘
       │                                     │                    │
       │                              ┌──────┴───────┐     ┌─────┴─────┐
       │                              │   ffmpeg     │     │    dbt    │
       │                              │ Video→mp4    │     │ staging + │
       │                              │ Lossless→mp3 │     │   marts   │
       │                              │ Extract audio│     └───────────┘
       │                              └──────┬───────┘
       │                                     │
       └─────────────────────────────────────┘
              GCS Output Bucket
         audio/{genre}/  +  video/{genre}/  +  stems/
```

## Services

| Service | Purpose | Free Tier |
|---|---|---|
| **Cloud Storage** | Input dropzone + output (organized by genre) | 5 GB |
| **Pub/Sub** | Event-driven trigger on file upload | 10 GB/mo |
| **Cloud Run** | Serverless Python processor (tag extraction, ffmpeg, Gemini) | 2M req/mo |
| **BigQuery** | Analytics warehouse (tracks, processing logs) | 1 TB queries, 10 GB storage |
| **Gemini (Vertex AI)** | AI genre classification from 30s audio clips | Pay-per-use (~$0.002/track) |
| **Secret Manager** | Spotify API credentials | 6 secrets free |
| **Cloud Build** | Container image builds | 120 min/day |
| **Looker Studio** | Live dashboard with charts + conversational analytics | Free |

## What It Does

### File Processing

| Input | Output |
|---|---|
| `.mp3` | BigQuery + `output/audio/{genre}/file.mp3` |
| `.wav`, `.aiff`, `.flac` | Converted to MP3 (320kbps), original discarded |
| `.mp4`, `.avi`, `.mkv` | Audio extracted + video kept → `output/audio/` + `output/video/` |
| `.vdjstems` | Copied to `output/stems/` |
| `._*` (Apple Double) | Skipped |
| Duplicate content | Detected via SHA256 → deleted from dropzone |

### Data Enrichment

- **ID3 tag extraction**: title, artist, album, genre, BPM, key
- **Mixed In Key energy**: Parsed from comment tag (e.g. "9A - 7" → energy 7/10)
- **Spotify enrichment**: Audio features (danceability, energy, valence) via Spotify API
- **Gemini genre analysis**: 30s audio clip analyzed by Gemini 2.5 Flash, overrides tag genre if confidence ≥ 70%

## Quick Start

### Prerequisites
- GCP project with billing enabled
- `gcloud` CLI installed and authenticated
- Terraform ≥ 1.5

### 1. Deploy Infrastructure

```bash
cd terraform/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project ID, billing account, region

terraform init
terraform plan
terraform apply
```

### 2. Build & Deploy Processor

```bash
cd ../processor/
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/dj-processor/dj-processor:latest
gcloud run services update dj-processor --region=REGION --image=REGION-docker.pkg.dev/PROJECT/dj-processor/dj-processor:latest
```

### 3. Enable Gemini Genre Analysis (optional)

```bash
gcloud run services update dj-processor --region=REGION --update-env-vars=GEMINI_GENRE_ENABLED=true
```

### 4. Deploy Dashboard

```bash
cd ../dashboard/
docker build -t dj-funk-dashboard .
docker run -d --name dj-dashboard -p 8082:8080 \
  -v ~/.config/gcloud/application_default_credentials.json:/gcp-creds.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/gcp-creds.json \
  -e PROJECT_ID=YOUR_PROJECT \
  dj-funk-dashboard
```

### 5. Test

```bash
# Upload a track
gsutil cp test.mp3 gs://PROJECT-dj-funk-dropzone/

# Wait 30s, then query
bq query "SELECT title, artist, genre, bpm, key, energy_level, gemini_genre FROM \`PROJECT.dj_funk.tracks\` ORDER BY ingested_at DESC LIMIT 10"

# View dashboard
open http://localhost:8082
```

## Cost

| Item | Typical Monthly Cost |
|---|---|
| 1000 tracks processed (no Gemini) | ~$0 (free tier) |
| 1000 tracks with Gemini genre | ~$2 |
| Dashboard (local container) | $0 |

Budget alerts at 50%, 80%, 100% of configured limit.

## Project Structure

```
gcp-dj-platform/
├── terraform/           # Infrastructure as Code
│   ├── main.tf          # Provider, APIs, service account
│   ├── storage.tf       # GCS buckets (input + output)
│   ├── pubsub.tf        # Event notifications
│   ├── cloud_run.tf     # Processor service + secrets
│   ├── bigquery.tf      # Dataset, tables
│   ├── monitoring.tf    # Budget alerts
│   ├── outputs.tf       # URLs, commands
│   └── disabled/        # Vertex AI (deferred — $48/mo endpoint)
├── processor/           # Cloud Run processor
│   ├── main.py          # Pub/Sub handler + all logic
│   ├── Dockerfile       # Python 3.12 + ffmpeg
│   └── requirements.txt
├── dashboard/           # Looker-style web UI
│   ├── app.py           # Flask + BigQuery + Chart.js
│   └── Dockerfile
├── bigquery/            # SQL resources
│   └── queries.sql      # Python UDFs, AI.CLASSIFY, analytics
├── scripts/             # Utilities
│   └── backfill_energy.py
├── PLAN.md              # Original implementation plan
└── README.md            # This file
```

## Related Repositories

- **XtremeTags** (`feat/gcp-migration` branch): Local pipeline with GCP bridge
  - `app/watchtower/bq_ingest.py` — BigQuery client for local→GCP sync
  - `app/watchtower/gcp_watchtower.py` — Dropzone→GCS bridge
  - `dbt_bq/` — dbt models for BigQuery
  - `terraform_gcp/` — Copy of GCP infrastructure code
