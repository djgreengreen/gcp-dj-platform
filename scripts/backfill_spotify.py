"""Backfill Spotify audio features for tracks missing spotify_id.

Queries BigQuery for tracks without Spotify enrichment, searches
Spotify API by title+artist, updates BigQuery with features.

Rate-limited to avoid hitting Spotify API caps. Resumable.
"""

import os, sys, json, time, re
from datetime import datetime, timezone
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from google.cloud import bigquery

PROJECT = os.environ.get("PROJECT_ID", "xtremetag-1984")
DATASET = "dj_funk"
TABLE = f"`{PROJECT}.{DATASET}.tracks`"
CACHE = Path("/tmp/spotify_cache.json")
BATCH_SIZE = 50


def get_spotify():
    cid = os.environ.get("SPOTIFY_CLIENT_ID", "")
    cs = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    if not cid or not cs:
        print("  ❌ SPOTIFY_CLIENT_ID / SECRET not set")
        return None
    try:
        auth = SpotifyClientCredentials(client_id=cid, client_secret=cs)
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        print(f"  ❌ Spotify auth failed: {e}")
        return None


def get_tracks_without_spotify(client, limit=5000):
    query = f"""
        SELECT track_id, title, artist
        FROM {TABLE}
        WHERE spotify_id IS NULL
        AND title IS NOT NULL
        LIMIT {limit}
    """
    rows = list(client.query(query).result())
    print(f"  → {len(rows)} tracks without Spotify enrichment")
    return rows


def search_spotify(sp, title, artist):
    """Search Spotify for the track. Returns first match or None."""
    queries = [
        f"track:{title} artist:{artist}",
        title,
    ]
    for q in queries:
        try:
            results = sp.search(q=q, type="track", limit=3)
            tracks = results.get("tracks", {}).get("items", [])
            if tracks:
                return tracks[0]
        except Exception:
            pass
    return None


def extract_spotify_data(track, spot):
    if not spot:
        return {}
    features = {}
    try:
        audio = sp.audio_features(spot["id"])
        if audio and audio[0]:
            features = {
                "spotify_id": spot["id"],
                "spotify_popularity": spot.get("popularity"),
                "spotify_danceability": audio[0].get("danceability"),
                "spotify_energy": audio[0].get("energy"),
                "spotify_valence": audio[0].get("valence"),
                "spotify_acousticness": audio[0].get("acousticness"),
                "spotify_instrumentalness": audio[0].get("instrumentalness"),
            }
    except Exception as e:
        print(f"  ⚠ Audio features error: {e}")
    return features


def update_bq(client, batch):
    """Update BigQuery rows with Spotify data using MERGE."""
    if not batch:
        return

    rows = []
    for b in batch:
        if b.get("spotify_id"):
            rows.append(b)

    if not rows:
        return

    # Use MERGE to update streaming buffer rows
    merge_sql = f"MERGE {TABLE} T USING ("
    unions = []
    params = {}
    for i, r in enumerate(rows):
        sets = []
        for k, v in r.items():
            if v is not None:
                if isinstance(v, (int, float)):
                    unions.append(f"SELECT @tid{i} AS tid, '{k}' AS fld, CAST(@val{i}_{k} AS FLOAT64) AS val")
                    params[f"tid{i}"] = r["track_id"]
                    params[f"val{i}_{k}"] = v
                else:
                    unions.append(f"SELECT @tid{i} AS tid, '{k}' AS fld, CAST(@val{i}_{k} AS STRING) AS val")
                    params[f"tid{i}"] = r["track_id"]
                    params[f"val{i}_{k}"] = str(v)

    if not unions:
        return

    # Use individual UPDATE statements instead
    job_config = bigquery.QueryJobConfig(query_parameters=[])
    for r in rows:
        sets = []
        params_list = []
        for k, v in r.items():
            if v is not None and k != "track_id":
                if isinstance(v, (int, float)):
                    sets.append(f"{k} = @{k}")
                    params_list.append(bigquery.ScalarQueryParameter(k, "FLOAT64", v))
                else:
                    sets.append(f"{k} = @{k}")
                    params_list.append(bigquery.ScalarQueryParameter(k, "STRING", str(v)))
        if not sets:
            continue
        params_list.append(bigquery.ScalarQueryParameter("tid", "STRING", r["track_id"]))
        sql = f"UPDATE {TABLE} SET {', '.join(sets)} WHERE track_id = @tid"
        try:
            client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params_list)).result()
        except Exception as e:
            if "streaming buffer" in str(e):
                pass  # skip streaming buffer rows
            else:
                print(f"  ⚠ Update error for {r.get('track_id','')[:12]}: {str(e)[:80]}")


def main():
    sp = get_spotify()
    if not sp:
        return

    client = bigquery.Client(project=PROJECT)
    tracks = get_tracks_without_spotify(client, limit=5000)

    matched = 0
    failed = 0
    batch = []

    for i, row in enumerate(tracks):
        track_id = row.track_id
        title = row.title
        artist = row.artist

        spot = search_spotify(sp, title, artist)
        if spot:
            features = extract_spotify_data(row, spot)
            if features:
                features["track_id"] = track_id
                batch.append(features)
                matched += 1
            else:
                failed += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0 or i == len(tracks) - 1:
            print(f"  [{i+1}/{len(tracks)}] {matched} matched, {failed} failed")

        if batch and (len(batch) >= BATCH_SIZE or i == len(tracks) - 1):
            update_bq(client, batch)
            print(f"  ✓ Updated {len(batch)} tracks")
            batch = []

        # Rate limit: be nice to Spotify
        time.sleep(0.3)

    print(f"\nDone! {matched} tracks enriched with Spotify data")


if __name__ == "__main__":
    main()
