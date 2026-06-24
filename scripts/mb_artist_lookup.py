"""MusicBrainz artist lookup — batch queries MB API, stores in BigQuery.

Usage:
    python3 mb_artist_lookup.py                    # Batch lookup all artists
    python3 mb_artist_lookup.py --resume           # Resume from cache
    python3 mb_artist_lookup.py --force            # Re-lookup even cached

Rate-limited to 1 req/s. Progress saved to /tmp/mb_cache.json
"""

import os, sys, json, time, re
from datetime import datetime, timezone
from pathlib import Path

import requests
from google.cloud import bigquery

PROJECT = os.environ.get("PROJECT_ID", "xtremetag-1984")
DATASET = "dj_funk"
TABLE = f"{PROJECT}.{DATASET}.musicbrainz_artists"
CACHE = Path("/tmp/mb_cache.json")

# MusicBrainz API — 1 req/s limit, identify ourselves
HEADERS = {
    "User-Agent": "XtremeTags/1.0 (dj-data-pipeline; louis.eudo@gmail.com)",
    "Accept": "application/json"
}
BASE = "https://musicbrainz.org/ws/2"


def get_artists_from_bq():
    """Fetch all unique artist names from dim_artist."""
    client = bigquery.Client(project=PROJECT)
    query = f"""
        SELECT artist_name, total_appearances
        FROM `{PROJECT}.dj_funk_production.dim_artist`
        ORDER BY total_appearances DESC
    """
    rows = list(client.query(query).result())
    artists = [row.artist_name for row in rows]
    print(f"  → {len(artists)} artists from dim_artist")
    return artists


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def save_cache(cache):
    CACHE.write_text(json.dumps(cache, indent=2))


def query_mb(artist_name):
    """Query MusicBrainz for an artist. Returns best match or None."""
    # Skip very short names (likely noise)
    if len(artist_name) < 3:
        return None

    # URL-encode the query
    import urllib.parse
    query = urllib.parse.quote(f'artist:"{artist_name}"')
    url = f"{BASE}/artist/?query={query}&fmt=json&limit=5"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠ HTTP {resp.status_code} for '{artist_name}'")
            return None

        data = resp.json()
        artists = data.get("artists", [])
        if not artists:
            return None

        # Pick best match: exact name match preferred, then score
        best = None
        for a in artists:
            m_name = a.get("name", "").lower().strip()
            if m_name == artist_name.lower().strip():
                best = a
                break
            if best is None:
                best = a

        if best:
            return {
                "artist_name": artist_name,
                "mbid": best.get("id"),
                "canonical_name": best.get("name"),
                "sort_name": best.get("sort-name"),
                "type": best.get("type"),  # Person, Group, etc.
                "gender": (best.get("gender") or ""),
                "country": (best.get("country") or ""),
                "disambiguation": (best.get("disambiguation") or ""),
                "score": data.get("count", 0),
                "matched_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        print(f"  ⚠ Error for '{artist_name}': {e}")

    return None


def insert_bq(client, batch):
    """Insert a batch of results into BigQuery."""
    if not batch:
        return
    errors = client.insert_rows_json(TABLE, batch)
    if errors:
        print(f"  ⚠ BQ insert errors: {errors}")
    else:
        print(f"  ✓ Inserted {len(batch)} rows to {TABLE}")


def ensure_table(client):
    """Create the BigQuery table if it doesn't exist."""
    schema = [
        bigquery.SchemaField("artist_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("mbid", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("canonical_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sort_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("gender", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("country", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("disambiguation", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("score", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("matched_at", "TIMESTAMP", mode="NULLABLE"),
    ]
    table = bigquery.Table(TABLE, schema=schema)
    table.clustering_fields = ["artist_name"]
    try:
        client.create_table(table)
        print(f"  ✓ Created table {TABLE}")
    except Exception:
        pass  # Table already exists


def main(resume=False, force=False):
    client = bigquery.Client(project=PROJECT)
    ensure_table(client)

    if resume or True:  # Default: only process unmatched
        # Always resume — only do unmatched artists
        cache = load_cache()
        already_matched = len(cache)
        artists = get_artists_from_bq()

        # Remove already-cached from the list
        new_artists = []
        for a in artists:
            if a not in cache or force:
                new_artists.append(a)

        print(f"  → {already_matched} already cached, {len(new_artists)} remaining")
        artists = new_artists
    else:
        cache = {}
        artists = get_artists_from_bq()

    total = len(artists)
    batch = []
    bq_batch_size = 100

    for idx, artist in enumerate(artists):
        if artist in cache and not force:
            continue

        result = query_mb(artist)
        if result:
            cache[artist] = result
            batch.append(result)

        # Progress report
        if (idx + 1) % 50 == 0 or idx == total - 1:
            matched = sum(1 for a in artists[:idx+1] if cache.get(a))
            print(f"  [{idx+1}/{total}] {matched} matched, {total-(idx+1)} remaining")

        # Periodic cache save and BQ insert
        if batch and (len(batch) >= bq_batch_size or idx == total - 1):
            insert_bq(client, batch)
            save_cache(cache)
            batch = []

        # Rate limit: 1 request per second
        time.sleep(1.1)

    save_cache(cache)
    print(f"\nDone! {len(cache)} artists looked up, {sum(1 for v in cache.values() if v and v.get('mbid'))} matched")

    # Summary
    matched = [v for v in cache.values() if v and v.get('mbid')]
    unmatched = [k for k, v in cache.items() if not v or not v.get('mbid')]
    print(f"  Matched: {len(matched)}")
    print(f"  Unmatched: {len(unmatched)}")
    if unmatched:
        print(f"  Examples: {unmatched[:10]}")


if __name__ == "__main__":
    resume = "--resume" in sys.argv
    force = "--force" in sys.argv
    main(resume=resume, force=force)
