// Dataform includes — reusable JavaScript helpers
// These work like dbt macros/Jinja, but in JavaScript

// ── Tag helper: check if a track has a specific tag ──────────────
function hasTag(tagName) {
  return `EXISTS(SELECT 1 FROM UNNEST(tags) tag WHERE tag = '${tagName}')`;
}

// ── Camelot key to musical key conversion ────────────────────────
function camelotToKey(camelot) {
  const map = {
    "1A": "Ab min",  "1B": "B maj",
    "2A": "Eb min",  "2B": "F# maj",
    "3A": "Bb min",  "3B": "Db maj",
    "4A": "F min",   "4B": "Ab maj",
    "5A": "C min",   "5B": "Eb maj",
    "6A": "G min",   "6B": "Bb maj",
    "7A": "D min",   "7B": "F maj",
    "8A": "A min",   "8B": "C maj",
    "9A": "E min",   "9B": "G maj",
    "10A": "B min",  "10B": "D maj",
    "11A": "F# min", "11B": "A maj",
    "12A": "C# min", "12B": "E maj",
  };
  return map[camelot] || null;
}

// ── BPM range classifier ─────────────────────────────────────────
function bpmRange(bpmCol) {
  return `CASE
    WHEN ${bpmCol} < 100 THEN 'slow'
    WHEN ${bpmCol} BETWEEN 100 AND 124 THEN 'mid'
    WHEN ${bpmCol} BETWEEN 125 AND 135 THEN 'uptempo'
    ELSE 'fast'
  END`;
}

// ── Energy label ─────────────────────────────────────────────────
function energyLabel(energyCol) {
  return `CASE
    WHEN ${energyCol} >= 8 THEN 'high'
    WHEN ${energyCol} >= 5 THEN 'mid'
    ELSE 'low'
  END`;
}

// ── Track type classifier from title ─────────────────────────────
function trackType(titleCol, artistCol) {
  return `CASE
    WHEN REGEXP_CONTAINS(LOWER(${titleCol}), r'\\bmashup\\b') THEN 'mashup'
    WHEN REGEXP_CONTAINS(LOWER(${titleCol}), r'\\bbootleg\\b') THEN 'bootleg'
    WHEN REGEXP_CONTAINS(LOWER(${artistCol}), r' vs\\.? ') THEN 'mashup'
    WHEN REGEXP_CONTAINS(LOWER(${titleCol}), r'\\btransition\\b') THEN 'transition'
    WHEN REGEXP_CONTAINS(LOWER(${titleCol}), r'\\bredrum\\b') THEN 'redrum'
    WHEN REGEXP_CONTAINS(LOWER(${titleCol}), r'\\bintro edit\\b') THEN 'intro_edit'
    ELSE 'normal'
  END`;
}

module.exports = {
  hasTag,
  camelotToKey,
  bpmRange,
  energyLabel,
  trackType
};
