-- ============================================================================
-- BigQuery AI UDFs & Enrichment Queries
-- Run AFTER terraform apply and first tracks are loaded.
-- ============================================================================

-- 1. AI Energy Classification (using BigQuery AI.CLASSIFY)
--    Labels tracks as Low/Medium/High energy based on Spotify audio features
-- ============================================================================
CREATE OR REPLACE FUNCTION `dj_funk.classify_energy`(energy FLOAT64)
RETURNS STRING
LANGUAGE sql
AS (
  CASE
    WHEN energy < 0.33 THEN 'Low Energy'
    WHEN energy < 0.66 THEN 'Medium Energy'
    ELSE 'High Energy'
  END
);

-- 2. AI Mood Classification using AI.CLASSIFY
--    Uses Gemini to classify mood from genre + audio features
-- ============================================================================
-- Run this as a batch UPDATE after tracks are loaded:
/*
UPDATE `dj_funk.tracks`
SET ai_mood = AI.CLASSIFY(
  FORMAT('Genre: %s, BPM: %.0f, Energy: %.2f, Valence: %.2f',
    COALESCE(genre, 'Unknown'),
    COALESCE(bpm, 0),
    COALESCE(spotify_energy, 0.5),
    COALESCE(spotify_valence, 0.5)),
  ['Dark', 'Uplifting', 'Euphoric', 'Chill', 'Aggressive', 'Groovy', 'Melancholic']
)
WHERE ai_mood IS NULL
  AND spotify_energy IS NOT NULL;
*/

-- 3. Python UDF: Genre normalizer
--    Normalizes messy genre tags into standard categories
-- ============================================================================
CREATE OR REPLACE FUNCTION `dj_funk.normalize_genre`(genre STRING)
RETURNS STRING
LANGUAGE python
OPTIONS (
  runtime_version = 'python-3.11',
  entry_point = 'normalize'
)
AS r'''
def normalize(genre):
    if not genre:
        return "Unknown"
    g = genre.lower().strip()
    mappings = {
        "deep house": "Deep House",
        "tech house": "Tech House",
        "techno": "Techno",
        "minimal": "Minimal",
        "progressive house": "Progressive House",
        "trance": "Trance",
        "drum and bass": "Drum & Bass",
        "dnb": "Drum & Bass",
        "dubstep": "Dubstep",
        "hip hop": "Hip Hop",
        "hip-hop": "Hip Hop",
        "r&b": "R&B",
        "pop": "Pop",
        "disco": "Disco",
        "funk": "Funk",
        "soul": "Soul",
        "jazz": "Jazz",
        "latin": "Latin",
        "afro house": "Afro House",
        "melodic techno": "Melodic Techno",
        "melodic house": "Melodic House",
        "organic house": "Organic House",
        "indie dance": "Indie Dance",
        "electronica": "Electronica",
        "breaks": "Breaks",
        "uk garage": "UK Garage",
        "bass": "Bass Music",
    }
    for pattern, canonical in mappings.items():
        if pattern in g:
            return canonical
    return genre.strip()
''';

-- 4. Useful analytics queries
-- ============================================================================

-- Top genres by track count
/*
SELECT
  `dj_funk.normalize_genre`(genre) AS clean_genre,
  COUNT(*) AS tracks,
  ROUND(AVG(bpm), 1) AS avg_bpm,
  ROUND(AVG(spotify_energy), 2) AS avg_energy
FROM `dj_funk.tracks`
WHERE genre IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
*/

-- Key compatibility (Camelot wheel — harmonic mixing)
/*
SELECT
  key_camelot,
  COUNT(*) AS tracks,
  ARRAY_AGG(STRUCT(title, artist, bpm) ORDER BY spotify_popularity DESC LIMIT 5) AS top_tracks
FROM `dj_funk.tracks`
WHERE key_camelot IS NOT NULL
GROUP BY 1
ORDER BY tracks DESC;
*/

-- Find tracks within BPM range of target, harmonically compatible
/*
DECLARE target_bpm FLOAT64 DEFAULT 128;
DECLARE target_key STRING DEFAULT '8A';

SELECT title, artist, bpm, key_camelot, spotify_energy
FROM `dj_funk.tracks`
WHERE bpm BETWEEN target_bpm - 5 AND target_bpm + 5
  AND key_camelot IN ('8A', '7A', '9A', '8B')  -- harmonic neighbors
  AND genre LIKE '%Tech%'
ORDER BY spotify_popularity DESC
LIMIT 20;
*/
