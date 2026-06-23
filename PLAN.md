# GCP DJ Music Platform — Implementation Plan

> **Goal:** Replace local XtremeTags dropzone with GCP Cloud Storage, add BigQuery analytics + Vertex AI enrichment, all deployed via Terraform. Learn the new GCP data stack hands-on.
>
> **Architecture:** MP3s land in GCS bucket → Pub/Sub event → Cloud Run processes metadata → BigQuery warehouse. Vertex AI for embeddings/similarity. Looker/Data Studio for dashboards.
>
> **Budget safety:** All free-tier eligible. Estimated $0-5/month. Budget alerts + hard caps in Terraform.

---

## What You Need to Provide

| # | Item | Why |
|---|---|---|
| 1 | **GCP Project ID** | Terraform needs a project to deploy into. Create at console.cloud.google.com |
| 2 | **Billing Account ID** | Format: `XXXXXX-XXXXXX-XXXXXX`. I won't store it — you'll set `TF_VAR_billing_account` as env var |
| 3 | **GCP region** | `australia-southeast1` (Sydney) recommended — lowest latency for you |
| 4 | **Service account key** | I'll have Terraform create one. You just need `gcloud auth application-default login` run once |
| 5 | **Spotify API creds** | Already in your env. We'll reuse for GCP enrichment (Cloud Run → Spotify) |
| 6 | **GDrive rclone config** | You already have this. We can optionally wire GCS→GDrive sync |

**You don't need to provide:** MP3 files, database dumps, or credentials in chat. I'll write all code, you run it.

---

## Architecture

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌──────────┐
│  GCS     │────▶│ Pub/Sub  │────▶│  Cloud Run   │────▶│ BigQuery │
│ Bucket   │     │ (events) │     │ (processing) │     │ (ware-   │
│ (mp3 in) │     └──────────┘     │              │     │  house)  │
└──────────┘                      │ - extract tag│     └────┬─────┘
                                  │ - spotify API│          │
                                  │ - audio feat │          │
                                  └──────────────┘     ┌────┴─────┐
                                                        │ Vertex AI│
                                                        │(embeddings│
                                                        │ similarity│
                                                        └──────────┘
```

### Services Used (and what you learn)

| GCP Service | Free Tier | What You Learn |
|---|---|---|
| **Cloud Storage** | 5 GB-months | Replaces local dropzone. Object lifecycle policies |
| **Pub/Sub** | 10 GB messages | Event-driven architecture. Streaming ingestion pattern |
| **Cloud Run** | 2M requests/month | Serverless compute. Containerized processing |
| **BigQuery** | 1 TB queries/month, 10 GB storage | Python UDFs, AI functions (`AI.CLASSIFY`), Graph queries, streaming inserts, fluid scaling |
| **Vertex AI** | $300 credit | Embedding generation, vector search, Gemini NL queries |
| **Secret Manager** | 6 secrets | Secure Spotify API key storage |
| **Cloud Monitoring** | Basic tier free | Budget alerts, dashboards |
| **Looker Studio** | Free | Conversational Analytics on your library |

**Total cost for 100-500 tracks/month: ~$0-3/month** (well within free tier)

---

## Implementation Phases

### Phase 1: Foundation — Terraform Project Setup
**Time: ~15 min | Task: 1-5**

1. Create GCP project structure on disk (`/root/gcp-dj-platform/`)
2. Terraform provider config, backend (local to start), variables
3. Enable required GCP APIs via Terraform
4. Budget alert at $5/month with notification
5. `terraform init && terraform plan` — verify clean

### Phase 2: Storage + Events — GCS + Pub/Sub
**Time: ~10 min | Task: 6-9**

6. Create GCS bucket with lifecycle policy (auto-delete files >30 days)
7. Create Pub/Sub topic for file upload events
8. Wire GCS notification → Pub/Sub on object finalize
9. Test: upload a test file, verify Pub/Sub message received

### Phase 3: Processing — Cloud Run
**Time: ~20 min | Task: 10-14**

10. Write Cloud Run processor (Python): reads Pub/Sub event, downloads MP3 from GCS, extracts tags with mutagen, calls Spotify API, inserts to BigQuery
11. Store Spotify API key in Secret Manager
12. Build container, push to Artifact Registry
13. Deploy Cloud Run service with Pub/Sub trigger
14. Test end-to-end: drop test MP3 → verify row in BigQuery

### Phase 4: BigQuery — Analytics Warehouse
**Time: ~15 min | Task: 15-19**

15. Create BigQuery dataset + tables (tracks, artists, genres, play_events)
16. Create Python UDF for genre classification via Spotify API
17. Create `AI.CLASSIFY` function for mood tagging from audio features
18. Set up streaming insert from Cloud Run processor
19. Run sample queries: top genres, BPM distribution, key compatibility

### Phase 5: Vertex AI — Embeddings + Similarity
**Time: ~15 min | Task: 20-23**

20. Generate track embeddings via Vertex AI text embeddings (track name + artist + genre)
21. Create vector index for similarity search
22. Query: "find tracks like this one" via vector similarity
23. Test conversational analytics: "show me tech house tracks around 128 BPM in Am"

### Phase 6: Visualization — Looker Studio
**Time: ~10 min | Task: 24-26**

24. Connect Looker Studio to BigQuery
25. Build dashboard: genre distribution, BPM/key wheel, recent additions
26. Enable Conversational Analytics on the dashboard

---

## What This Looks Like After Phase 6

```
You drop MP3s:
  gsutil cp new_track.mp3 gs://dj-funk-dropzone/

Within seconds:
  → Pub/Sub fires event
  → Cloud Run extracts tags, fetches Spotify metadata, audio features
  → Row appears in BigQuery
  → Vertex AI embedding generated
  → Dashboard updates

You can then:
  SELECT * FROM tracks WHERE genre LIKE '%tech house%' AND bpm BETWEEN 126 AND 130
  -- Or just ASK: "what tech house tracks in Am should I play next?"
```

---

## Files That Will Be Created

```
/root/gcp-dj-platform/
├── terraform/
│   ├── main.tf              # Provider, APIs, project config
│   ├── variables.tf         # All input variables
│   ├── outputs.tf           # Bucket URL, service URLs
│   ├── storage.tf           # GCS bucket + lifecycle
│   ├── pubsub.tf            # Topics + subscriptions
│   ├── cloud_run.tf         # Service + IAM
│   ├── bigquery.tf          # Dataset, tables, schemas, UDFs
│   ├── vertex_ai.tf         # Embedding endpoints
│   ├── monitoring.tf        # Budget alerts
│   └── terraform.tfvars     # Your values (gitignored)
├── processor/
│   ├── main.py              # Cloud Run handler
│   ├── requirements.txt     # Python deps
│   └── Dockerfile           # Container build
└── README.md                # Setup instructions
```

---

## Pre-flight Checklist

Before I start writing Terraform, confirm:

- [ ] You have a GCP project created (or want me to guide you through `gcloud projects create`)
- [ ] You've run `gcloud auth application-default login`
- [ ] You know your billing account ID (`gcloud billing accounts list`)
- [ ] Region preference: Sydney (`australia-southeast1`)?

Reply with these and I'll start writing the Terraform + processor code immediately.
