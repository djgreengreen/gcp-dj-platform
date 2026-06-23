"""Backfill energy_level from Mixed In Key comment tags in output bucket.

Reads tracks without energy_level from BigQuery, downloads the MP3 from
the output bucket, extracts comment/energy, updates BigQuery.
"""

import os
import sys
import re
from io import BytesIO
from google.cloud import bigquery, storage
from mutagen.mp3 import MP3

PROJECT = os.environ.get("PROJECT_ID", "xtremetag-1984")
DATASET = os.environ.get("BQ_DATASET", "dj_funk")
BUCKET = os.environ.get("OUTPUT_BUCKET", "xtremetag-1984-dj-funk-output")
TABLE = f"`{PROJECT}.{DATASET}.tracks`"


def parse_energy(comment: str) -> int | None:
    """Parse Mixed In Key energy from comment."""
    if not comment:
        return None
    m = re.search(r"energy\s*(\d+)", comment, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*$", comment)
    if m:
        e = int(m.group(1))
        if 1 <= e <= 10:
            return e
    return None


def main():
    bq = bigquery.Client(project=PROJECT)
    gcs = storage.Client(project=PROJECT)
    bucket_obj = gcs.bucket(BUCKET)

    # Find tracks missing energy_level but with output paths
    query = f"""
        SELECT track_id, title, artist, genre, file_path
        FROM {TABLE}
        WHERE energy_level IS NULL
        AND title IS NOT NULL
        AND genre IS NOT NULL
        LIMIT 500
    """
    rows = list(bq.query(query).result())
    print(f"Found {len(rows)} tracks without energy_level")

    updated = 0
    failed = 0
    skipped = 0

    for row in rows:
        track_id = row.track_id
        title = row.title or "Unknown"
        artist = row.artist or "Unknown Artist"
        genre = row.genre or "Unknown"

        # Build output path: {genre}/{artist} - {title}.mp3
        # Sanitize same way as processor
        genre_safe = genre.replace("/", "-").strip()
        artist_safe = artist.replace("/", "-").strip()[:100]
        title_safe = title.replace("/", "-").strip()[:200]
        blob_name = f"{genre_safe}/{artist_safe} - {title_safe}.mp3"

        blob = bucket_obj.blob(blob_name)
        if not blob.exists():
            # Try without artist prefix
            blob_name2 = f"{genre_safe}/{title_safe}.mp3"
            blob = bucket_obj.blob(blob_name2)
        if not blob.exists():
            # Try audio/ prefix
            blob_name3 = f"audio/{genre_safe}/{artist_safe} - {title_safe}.mp3"
            blob = bucket_obj.blob(blob_name3)
        if not blob.exists():
            skipped += 1
            continue

        try:
            data = blob.download_as_bytes()
            audio = MP3(BytesIO(data))

            comment = None
            energy = None
            if audio.tags:
                comms = audio.tags.getall("COMM")
                for c in comms:
                    if hasattr(c, "text"):
                        texts = c.text
                        comment = str(texts[0]).strip() if isinstance(texts, list) and texts else str(texts).strip()
                        break

                if comment:
                    energy = parse_energy(comment)

            if energy:
                merge_query = f"""
                    MERGE {TABLE} T
                    USING (SELECT @track_id AS tid, @energy AS en, @comment AS cm) S
                    ON T.track_id = S.tid
                    WHEN MATCHED THEN UPDATE SET energy_level = S.en, comment = S.cm
                """
                from google.cloud import bigquery as bq_mod
                job_config = bq_mod.QueryJobConfig(
                    query_parameters=[
                        bq_mod.ScalarQueryParameter("energy", "INT64", energy),
                        bq_mod.ScalarQueryParameter("comment", "STRING", comment),
                        bq_mod.ScalarQueryParameter("track_id", "STRING", track_id),
                    ]
                )
                bq.query(merge_query, job_config=job_config).result()
                updated += 1
                print(f"  ✅ {title[:50]} → Energy {energy} ({comment})")
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            print(f"  ❌ {title[:50]}: {e}")

    print(f"\nDone: {updated} updated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
