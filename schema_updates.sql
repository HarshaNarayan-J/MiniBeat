-- =========================================================
-- Run this AFTER your original schema.sql
-- =========================================================
USE spotify_clone;

-- Search performance (LIKE '%q%' still works without these,
-- but this keeps things fast if you add more songs later)
ALTER TABLE Songs ADD INDEX idx_title (title);
ALTER TABLE Artists ADD INDEX idx_artist_name (artist_name);

-- ---------------------------------------------------------
-- Point file_url at real local files.
-- Put your actual mp3s in minibeat/static/audio/
-- and name them to match, e.g. song1.mp3, song2.mp3 ...
-- Then update the rows, e.g.:
-- ---------------------------------------------------------
-- UPDATE Songs SET file_url = '/audio/song1.mp3' WHERE song_id = 1;
-- UPDATE Songs SET file_url = '/audio/song2.mp3' WHERE song_id = 2;
-- ... etc for however many real tracks you have.

-- Quick way to bulk-rename if you just number them 1..50 to match song_id:
-- UPDATE Songs SET file_url = CONCAT('/audio/song', song_id, '.mp3');
-- (only run this once every song_id has a matching static/audio/songN.mp3 file)
