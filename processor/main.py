# GCP DJ Platform — Cloud Run Processor
# Handles Pub/Sub events when MP3s land in GCS bucket.
# Extracts metadata tags, fetches Spotify enrichment, writes to BigQuery.

import base64
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone

import functions_framework
from google.cloud import bigquery, storage

import mutagen
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


# ── Init clients (lazy, on first request) ─────────────────────────
_clients: dict = {}


def _get_spotify():
    """Lazy Spotify client. Returns None if not configured."""
    if "spotify" not in _clients:
        client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            print("Spotify not configured — skipping enrichment")
            _clients["spotify"] = None
            return None
        auth = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        _clients["spotify"] = spotipy.Spotify(auth_manager=auth)
    return _clients["spotify"]


def _get_bq():
    if "bq" not in _clients:
        _clients["bq"] = bigquery.Client()
    return _clients["bq"]


def _get_gcs():
    if "gcs" not in _clients:
        _clients["gcs"] = storage.Client()
    return _clients["gcs"]


# ── Main entrypoint ────────────────────────────────────────────────

@functions_framework.cloud_event
def process_track(cloud_event):
    """CloudEvent-triggered handler for Pub/Sub push subscription."""
    start = time.time()
    data = cloud_event.data

    if not data:
        print("No data in event, skipping")
        return ("skipped", 204)

    # Pub/Sub wraps in base64
    message = data.get("message", {})
    msg_data = message.get("data", "")
    msg_id = message.get("message_id", "unknown")

    if msg_data:
        payload = json.loads(base64.b64decode(msg_data))
    else:
        payload = data  # Direct push might not wrap

    # Extract GCS object info
    bucket_name = payload.get("bucket", "")
    object_name = payload.get("name", "")

    if not bucket_name or not object_name:
        print(f"Invalid payload: {payload}")
        log_event(msg_id, "", "error", "Missing bucket/name", time.time() - start)
        return ("error", 400)

    # Filename and extension
    filename = object_name.split("/")[-1]  # basename
    ext = Path(filename).suffix.lower()

    # ── Filtering (same rules as local watchtower/watcher.py) ──────────
    # Skip Apple Double ._ files
    if filename.startswith("._"):
        print(f"Skipping Apple Double: {object_name}")
        return ("skipped", 204)

    # Skip hidden files
    if filename.startswith("."):
        print(f"Skipping hidden: {object_name}")
        return ("skipped", 204)

    # Skip ignored extensions
    IGNORE_EXTS = {".asd", ".ini", ".log", ".tmp", ".dat", ".cue",
                   ".m3u", ".m3u8", ".nfo", ".sfv", ".md5", ".db"}
    if ext in IGNORE_EXTS:
        print(f"Skipping ignored ext: {object_name}")
        return ("skipped", 204)

    # Skip ignored directories (any path segment)
    IGNORE_DIRS = {"#recycle", "#recycle.bin", ".trash", ".tmp",
                   "@eaDir", ".synology", "test_final", "test_sync"}
    path_parts = set(object_name.split("/"))
    if path_parts & IGNORE_DIRS:
        print(f"Skipping ignored dir: {object_name}")
        return ("skipped", 204)

    # Handle .vdjstems files (VirtualDJ stems — copy to output stems/ folder)
    if ext == ".vdjstems":
        print(f"Handling stems file: {object_name}")
        copy_stems(bucket_name, object_name, filename)
        return ("ok", 200)

    # Determine file type
    VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"}
    AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aiff", ".ogg"}
    LOSSLESS_EXTS = {".wav", ".aiff", ".flac"}  # convert to mp3

    is_video = ext in VIDEO_EXTS
    is_audio = ext in AUDIO_EXTS
    needs_mp3_convert = ext in LOSSLESS_EXTS

    if not is_video and not is_audio:
        print(f"Skipping unsupported format: {object_name}")
        return ("skipped", 204)

    print(f"Processing: gs://{bucket_name}/{object_name} ({'video' if is_video else 'audio'})")

    try:
        # Content-based dedup
        content_hash = get_content_hash(bucket_name, object_name)
        if content_hash and is_duplicate(content_hash):
            print(f"Duplicate content — deleting: {object_name}")
            delete_from_dropzone(bucket_name, object_name)
            return ("skipped (duplicate)", 204)

        # Determine the audio file path for Gemini analysis
        local_audio_for_genre = None

        if is_video:
            # ── Video processing ────────────────────────────────────
            local_video = download_file(bucket_name, object_name)

            if ext != ".mp4":
                local_video = convert_video_to_mp4(local_video)

            local_audio = extract_audio_from_video(local_video)
            local_audio_for_genre = local_audio

            audio_track = extract_metadata_from_file(local_audio, content_hash)
            audio_track["file_path"] = f"gs://{bucket_name}/{object_name} (audio)"
            audio_track = enrich_spotify(audio_track)
            audio_track = enrich_gemini_genre(audio_track, local_audio)
            insert_bigquery(audio_track)

            genre = audio_track.get("genre", "Unknown")
            upload_to_output(local_audio, f"audio/{genre}/{Path(local_audio).name}")
            upload_to_output(local_video, f"video/{genre}/{Path(local_video).name}")

            Path(local_video).unlink(missing_ok=True)
            Path(local_audio).unlink(missing_ok=True)

        elif needs_mp3_convert:
            # ── Lossless → MP3 conversion ──────────────────────────
            local_file = download_file(bucket_name, object_name)
            local_mp3 = convert_audio_to_mp3(local_file)

            track = extract_metadata_from_file(local_mp3, content_hash)
            track["file_path"] = f"gs://{bucket_name}/{object_name} (converted to mp3)"
            track = enrich_spotify(track)
            track = enrich_gemini_genre(track, local_mp3)
            insert_bigquery(track)

            genre = track.get("genre", "Unknown")
            upload_to_output(local_mp3, f"audio/{genre}/{Path(local_mp3).name}")
            Path(local_mp3).unlink(missing_ok=True)
            Path(local_file).unlink(missing_ok=True)

        else:
            # ── Standard audio (mp3, m4a, ogg) ────────────────────
            local_file = download_file(bucket_name, object_name)
            track = extract_metadata_from_file(local_file, content_hash)
            track = enrich_spotify(track)
            track = enrich_gemini_genre(track, local_file)
            insert_bigquery(track)

            genre = track.get("genre", "Unknown")
            upload_to_output(local_file, f"audio/{genre}/{Path(local_file).name}")
            Path(local_file).unlink(missing_ok=True)

        # Delete from dropzone
        delete_from_dropzone(bucket_name, object_name)

        elapsed = (time.time() - start) * 1000
        print(f"Done: {object_name} ({elapsed:.0f}ms)")
        log_event(msg_id, object_name, "success", "", elapsed)
        return ("ok", 200)

    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"Error processing {object_name}: {e}")
        log_event(msg_id, object_name, "error", str(e)[:1000], elapsed)
        return ("error", 500)


# ── File I/O helpers ──────────────────────────────────────────────

def download_file(bucket: str, name: str) -> str:
    """Download file from GCS to local /tmp. Returns local path."""
    gcs = _get_gcs()
    blob = gcs.bucket(bucket).blob(name)
    local_path = f"/tmp/{name.split('/')[-1]}"
    blob.download_to_filename(local_path)
    return local_path


def upload_to_output(local_path: str, dest_name: str):
    """Upload local file to output bucket."""
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if not output_bucket:
        print("No OUTPUT_BUCKET configured — skipping upload")
        return
    gcs = _get_gcs()
    blob = gcs.bucket(output_bucket).blob(dest_name)
    blob.upload_from_filename(local_path)
    print(f"Uploaded: gs://{output_bucket}/{dest_name}")


# ── Metadata extraction ────────────────────────────────────────────

def extract_metadata_from_file(filepath: str, content_hash: str = "") -> dict:
    """Read local file and extract all ID3 tags."""
    data = Path(filepath).read_bytes()

    track = {
        "track_id": hashlib.sha256(filepath.encode()).hexdigest(),
        "file_path": filepath,
        "file_size_mb": round(len(data) / (1024 * 1024), 2),
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }

    # Parse ID3 tags
    try:
        audio = MP3(BytesIO(data))
        if audio.tags:
            tags = audio.tags
            track["title"] = _get_tag(tags, "TIT2")
            track["artist"] = _get_tag(tags, "TPE1")
            track["album"] = _get_tag(tags, "TALB")
            track["genre"] = _get_tag(tags, "TCON")

            # BPM
            bpm_tag = _get_tag(tags, "TBPM")
            if bpm_tag:
                try:
                    track["bpm"] = float(bpm_tag)
                except ValueError:
                    pass

            # Key
            initial_key = _get_tag(tags, "TKEY")
            if initial_key:
                track["key"] = initial_key

            # Comment — Mixed In Key energy level is stored here
            comment = _get_comment(tags)
            if comment:
                track["comment"] = comment
                energy = _parse_mik_energy(comment)
                if energy:
                    track["energy_level"] = energy

        track["duration_sec"] = round(audio.info.length, 1) if audio.info.length else None
        track["bitrate_kbps"] = audio.info.bitrate // 1000 if audio.info.bitrate else None
        track["sample_rate_hz"] = audio.info.sample_rate
    except Exception as e:
        print(f"Tag extraction warning: {e}")

    return track


def _get_tag(tags, frame_id: str) -> str | None:
    """Safely extract an ID3 text frame."""
    frame = tags.get(frame_id)
    if frame and hasattr(frame, "text"):
        texts = frame.text
        if isinstance(texts, list) and texts:
            return str(texts[0]).strip()
        return str(texts).strip()
    return None


def _get_comment(tags) -> str | None:
    """Extract comment from ID3 COMM frame(s).
    Mixed In Key writes energy level here."""
    # Try COMM frame (list of comments with lang/desc/text)
    comm_frames = tags.getall("COMM")
    for comm in comm_frames:
        if hasattr(comm, "text"):
            texts = comm.text
            if isinstance(texts, list) and texts:
                return str(texts[0]).strip()
            return str(texts).strip()
    # Fallback: try TXXX:Comment or TXXX:EnergyLevel
    for frame_id in ["TXXX:Comment", "TXXX:comment", "TXXX:ENERGYLEVEL",
                      "TXXX:EnergyLevel", "TXXX:energy"]:
        val = _get_tag(tags, frame_id)
        if val:
            return val
    return None


def _parse_mik_energy(comment: str) -> int | None:
    """Parse Mixed In Key energy level from comment tag.

    Common formats:
        "Energy 7"        → 7
        "energy 8"        → 8
        "8A - 128 - 7"    → 7  (key - bpm - energy)
        "7"               → 7
        "Energy Level: 5" → 5
    """
    import re
    if not comment:
        return None
    # "Energy N" or "energy N" pattern
    m = re.search(r"energy\s*(\d+)", comment, re.IGNORECASE)
    if m:
        return int(m.group(1))
    # "key - bpm - energy" triple (Mixed In Key format)
    m = re.search(r"(\d+)\s*$", comment)
    if m:
        energy = int(m.group(1))
        if 1 <= energy <= 10:
            return energy
    return None


# ── Spotify enrichment ─────────────────────────────────────────────

def enrich_spotify(track: dict) -> dict:
    """Search Spotify for the track and pull audio features."""
    sp = _get_spotify()
    if sp is None:
        return track
    artist = track.get("artist", "")
    title = track.get("title", "")

    if not artist or not title:
        return track

    query = f"track:{title} artist:{artist}"
    try:
        results = sp.search(q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if items:
            spot = items[0]
            track["spotify_id"] = spot["id"]
            track["spotify_popularity"] = spot.get("popularity")

            # Audio features
            features = sp.audio_features(spot["id"])
            if features and features[0]:
                f = features[0]
                track["spotify_danceability"] = f.get("danceability")
                track["spotify_energy"] = f.get("energy")
                track["spotify_valence"] = f.get("valence")
                track["spotify_acousticness"] = f.get("acousticness")
                track["spotify_instrumentalness"] = f.get("instrumentalness")
    except Exception as e:
        print(f"Spotify enrich failed: {e}")

    return track


# ── Gemini genre detection ──────────────────────────────────────────

def enrich_gemini_genre(track: dict, local_audio_path: str) -> dict:
    """Use Gemini via google-genai SDK to classify genre from audio clip.

    Only runs when GEMINI_GENRE_ENABLED=true env var is set.
    """
    if os.environ.get("GEMINI_GENRE_ENABLED", "").lower() not in ("true", "1", "yes"):
        return track

    try:
        from google import genai
        from google.genai import types

        # Extract 30-second clip
        clip_path = _extract_audio_clip(local_audio_path, duration=30)
        with open(clip_path, "rb") as f:
            audio_bytes = f.read()
        Path(clip_path).unlink(missing_ok=True)

        GENRE_PROMPT = """Analyze this 30-second audio clip and identify the music genre. Return ONLY JSON: {"genre": "Genre Name", "confidence": 0.95}. Genres: Deep House, Tech House, Techno, Progressive House, Trance, Drum & Bass, Dubstep, Hip Hop, Pop, Disco, Funk, Soul, Jazz, Latin, Afro House, Melodic Techno, Minimal, Breaks, UK Garage, Bass Music, Electronica, Ambient, Downtempo, Reggaeton, Dance Pop, EDM, Hardstyle, Hardcore, R&B, Rock, Indie, Other."""

        client = genai.Client(
            vertexai=True,
            project=os.environ["PROJECT_ID"],
            location=os.environ.get("GCP_REGION", "australia-southeast1"),
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(text=GENRE_PROMPT),
                        types.Part(
                            inline_data=types.Blob(
                                data=audio_bytes, mime_type="audio/mpeg"
                            )
                        ),
                    ]
                )
            ],
        )

        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)

        gemini_genre = result.get("genre", "").strip()
        confidence = result.get("confidence", 0.0)

        if gemini_genre and confidence > 0.5:
            track["gemini_genre"] = gemini_genre
            track["gemini_genre_confidence"] = confidence
            if confidence >= 0.7:
                print(f"Gemini genre: {gemini_genre} ({confidence:.0%}) — overriding tags")
                track["genre"] = gemini_genre
            else:
                print(f"Gemini genre: {gemini_genre} ({confidence:.0%}) — keeping tags")

    except ImportError:
        print("Gemini not available — install google-genai")
    except Exception as e:
        print(f"Gemini genre detection failed: {e}")

    return track


def _extract_audio_clip(filepath: str, duration: int = 30) -> str:
    """Extract first N seconds of audio as a temp mp3 file."""
    out_path = f"/tmp/clip_{os.getpid()}.mp3"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath, "-t", str(duration),
         "-c:a", "libmp3lame", "-b:a", "128k", out_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio clip extraction failed: {result.stderr[:200]}")
    return out_path


# ── BigQuery insert ────────────────────────────────────────────────

def insert_bigquery(track: dict):
    """Stream insert track into BigQuery."""
    bq = _get_bq()
    dataset = os.environ.get("BQ_DATASET", "dj_funk")
    table_id = f"{os.environ['PROJECT_ID']}.{dataset}.tracks"

    # Clean: only include fields that exist in schema
    allowed = {
        "track_id", "file_path", "file_size_mb", "title", "artist", "album",
        "genre", "bpm", "key", "duration_sec", "bitrate_kbps", "sample_rate_hz",
        "spotify_id", "spotify_popularity", "spotify_danceability",
        "spotify_energy", "spotify_valence", "spotify_acousticness",
        "spotify_instrumentalness", "gemini_genre", "gemini_genre_confidence",
        "energy_level", "comment",
        "ingested_at", "processed_at",
    }
    row = {
        k: v for k, v in track.items()
        if k in allowed and v is not None
    }
    row["processed_at"] = datetime.now(timezone.utc).isoformat()

    errors = bq.insert_rows_json(table_id, [row])
    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")


def log_event(event_id: str, file_path: str, status: str,
              error: str, duration_ms: float):
    """Record processing attempt in BigQuery."""
    bq = _get_bq()
    dataset = os.environ.get("BQ_DATASET", "dj_funk")
    table_id = f"{os.environ['PROJECT_ID']}.{dataset}.processing_log"

    row = {
        "event_id": event_id,
        "file_path": file_path,
        "status": status,
        "error_message": error or None,
        "duration_ms": int(duration_ms),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    bq.insert_rows_json(table_id, [row])


# ── Content dedup & cleanup ─────────────────────────────────────

def get_content_hash(bucket: str, name: str) -> str:
    """SHA256 of first 1MB of file content (same as local watcher.py)."""
    try:
        gcs = _get_gcs()
        blob = gcs.bucket(bucket).blob(name)
        # Read first 1MB for hashing
        data = blob.download_as_bytes(start=0, end=1024 * 1024)
        return hashlib.sha256(data).hexdigest()[:32]
    except Exception as e:
        print(f"Content hash failed: {e}")
        return ""


def is_duplicate(content_hash: str) -> bool:
    """Check if this content hash already exists in BigQuery."""
    if not content_hash:
        return False
    try:
        bq = _get_bq()
        dataset = os.environ.get("BQ_DATASET", "dj_funk")
        query = (
            f"SELECT 1 FROM `{os.environ['PROJECT_ID']}.{dataset}.tracks` "
            "WHERE content_hash = @hash LIMIT 1"
        )
        from google.cloud import bigquery
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("hash", "STRING", content_hash),
            ]
        )
        result = bq.query(query, job_config=job_config).result()
        return result.total_rows > 0
    except Exception:
        return False


def delete_from_dropzone(bucket: str, name: str):
    """Delete processed file from the dropzone bucket."""
    try:
        gcs = _get_gcs()
        blob = gcs.bucket(bucket).blob(name)
        blob.delete()
        print(f"Deleted from dropzone: {name}")
    except Exception as e:
        print(f"Failed to delete {name}: {e}")


def copy_to_output_bucket(source_bucket: str, object_name: str, track: dict):
    """DEPRECATED — use upload_to_output() instead."""
    pass


# ── Audio/Video conversion ────────────────────────────────────────

def convert_video_to_mp4(filepath: str) -> str:
    """Convert video to mp4 using ffmpeg. Returns path to mp4 file."""
    p = Path(filepath)
    if p.suffix.lower() == ".mp4":
        return filepath
    out_path = str(p.with_suffix(".mp4"))
    print(f"Converting video: {p.name} → mp4")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath,
         "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
         "-map_metadata", "0", "-movflags", "+faststart", out_path],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Video conversion failed: {result.stderr[:500]}")
    Path(filepath).unlink(missing_ok=True)
    return out_path


def extract_audio_from_video(filepath: str) -> str:
    """Extract audio track from video file as mp3. Returns path to mp3."""
    p = Path(filepath)
    out_path = str(p.with_suffix(".mp3"))
    print(f"Extracting audio from video: {p.name}")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath,
         "-vn", "-c:a", "libmp3lame", "-b:a", "320k",
         "-map_metadata", "0", "-id3v2_version", "3", out_path],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {result.stderr[:500]}")
    return out_path


def convert_audio_to_mp3(filepath: str) -> str:
    """Convert lossless audio (WAV/AIF/FLAC) to mp3. Returns path to mp3."""
    p = Path(filepath)
    out_path = str(p.with_suffix(".mp3"))
    print(f"Converting audio to mp3: {p.name}")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", filepath,
         "-c:a", "libmp3lame", "-b:a", "320k",
         "-map_metadata", "0", "-id3v2_version", "3", out_path],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio conversion failed: {result.stderr[:500]}")
    Path(filepath).unlink(missing_ok=True)  # discard original
    return out_path


def copy_stems(source_bucket: str, object_name: str, filename: str):
    """Copy VirtualDJ .vdjstems file to output bucket stems/ folder."""
    output_bucket = os.environ.get("OUTPUT_BUCKET", "")
    if not output_bucket:
        print("No OUTPUT_BUCKET configured — skipping stems copy")
        return

    gcs = _get_gcs()
    dest_name = f"stems/{filename}"
    source_blob = gcs.bucket(source_bucket).blob(object_name)
    dest_blob = gcs.bucket(output_bucket).blob(dest_name)
    dest_blob.rewrite(source_blob)
    print(f"Copied stems to output: gs://{output_bucket}/{dest_name}")


# Needed for in-memory MP3 parsing
from io import BytesIO
from pathlib import Path
