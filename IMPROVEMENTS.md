# Improvements & Next Steps

## Implemented

### Phase 1: Core Pipeline ✅
- [x] GCS dropzone bucket with lifecycle policies
- [x] Pub/Sub event notifications on upload
- [x] Cloud Run processor (Python, ffmpeg, mutagen)
- [x] BigQuery warehouse with time-partitioned tables
- [x] Terraform IaC with budget alerts
- [x] Content-based deduplication (SHA256 of first 1MB)
- [x] Processed files deleted from dropzone

### Phase 2: Audio/Video Handling ✅
- [x] WAV/AIFF/FLAC → MP3 conversion (320kbps, original discarded)
- [x] Video processing: extract audio + keep video in output/video/
- [x] Apple Double `._*` files skipped
- [x] VirtualDJ `.vdjstems` → output/stems/
- [x] Ignored directory filtering (#recycle, .trash, etc.)

### Phase 3: AI Enrichment ✅
- [x] Gemini 2.5 Flash genre classification from 30s audio clips
- [x] Togglable via `GEMINI_GENRE_ENABLED` env var
- [x] Genre override when confidence ≥ 70%
- [x] Mixed In Key energy extraction from comment tag
- [x] Spotify audio features enrichment

### Phase 4: Analytics & Visualization ✅
- [x] Looker-style dashboard with Chart.js (genre pie, BPM histogram)
- [x] Conversational analytics (NL → SQL)
- [x] Gemini genre confidence badges in table
- [x] dbt staging + marts models for BigQuery
- [x] Python UDF for genre normalization

### Phase 5: Operations ✅
- [x] Budget alert (5 AUD/month, 50/80/100% thresholds)
- [x] Processing log table for observability
- [x] Dead letter topic for failed messages
- [x] Cloud Run error monitoring alert
- [x] IAM service account with least privilege

---

## Future Improvements

### Cost & Performance

| Improvement | Impact | Effort |
|---|---|---|
| **Spotify enrichment in processor** | Richer audio features (danceability, energy, valence) | Low — API keys already wired |
| **Gemini batch mode** | Process multiple tracks per Gemini call, reduce cost 5x | Medium |
| **Cloud Run GPU (if needed)** | Faster audio analysis for large batches | Medium |
| **GCS lifecycle: archive to Archive class** | Reduce storage cost for old files | Low |

### Data Quality

| Improvement | Why |
|---|---|
| **Genre confidence from Gemini < 70% → flag for review** | Currently low-confidence results are silently kept as tags |
| **dbt tests for data quality** | Null checks on required fields, BPM range validation, key format |
| **Duplicate detection improvements** | Currently uses first 1MB hash — full file hash would be more precise |

### Features

| Improvement | Description |
|---|---|
| **BigQuery `AI.CLASSIFY` for mood tagging** | Use BQ AI functions to classify mood (Dark/Uplifting/Chill) from audio features |
| **BigQuery Python UDF for genre normalization** | Deploy the `normalize_genre` UDF (already written in `bigquery/queries.sql`) |
| **BigQuery Graph for artist networks** | Model collaborations and remix chains as a graph |
| **Vertex AI embeddings for similarity search** | "Find tracks like this one" — defer due to $48/mo endpoint cost |
| **Continuous queries for real-time analytics** | Streaming aggregation of genre distributions as tracks flow in |
| **Pub/Sub dead letter replay** | Re-process failed tracks after fixing bugs |

### Infrastructure

| Improvement | Why |
|---|---|
| **Terraform remote state (GCS backend)** | Team collaboration, state locking |
| **CI/CD pipeline for processor** | Auto-build and deploy on git push |
| **Cloud Run revision tagging** | Rollback capability |
| **Custom domain for dashboard** | Instead of IP:port |
| **HTTPS for dashboard** | Currently plain HTTP |

### XtremeTags Integration

| Improvement | Description |
|---|---|
| **Local → GCS bridge** | `gcp_watchtower.py` already written — wire into main loop |
| **PostgreSQL → BigQuery batch migration** | `--gcp-migrate N` flag built — run on full library |
| **Dual-write mode** | Process locally AND push to GCP simultaneously |
| **Replace GDrive with GCS output bucket** | Remove rclone dependency entirely |

---

## Known Issues

1. **Duplicate tracks from re-uploads**: Content-based dedup uses first 1MB hash — identical files with different names may slip through if first MB differs (unlikely for audio).
2. **Gemini API permissions**: `roles/aiplatform.user` must be granted to the Cloud Run service account. IAM propagation can take 2-5 minutes.
3. **BigQuery streaming buffer**: Recently streamed rows (~90 min) can't be updated via UPDATE — use MERGE instead.
4. **Spotify API not configured**: Enrichment runs but silently skips. Add credentials to Secret Manager and set `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` env vars.
5. **Dashboard on external IP**: Runs on plain HTTP. Use SSH tunnel or Cloud Run deployment for secure access.
