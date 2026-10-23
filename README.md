# MiniBeat — Setup

This has been fully built, run, and tested end-to-end (backend, database,
search, recommendations, play tracking, and real audio playback all
confirmed working). Here's how to get it running on your machine.

## 1. Database
```bash
mysql -u root -p < schema.sql
mysql -u root -p spotify_clone < schema_updates.sql
```
`schema_updates.sql` adds search indexes AND points 10 songs at real
demo audio files already included in `static/audio/` (song_ids
1, 2, 5, 8, 11, 14, 20, 24, 27, 39). Everything else in the database is
untouched from your original schema.

## 2. Python env
```bash
pip install flask mysql-connector-python
```

## 3. Configure DB credentials
Open `app.py`, edit `DB_CONFIG` near the top with your own MySQL
username/password:
```python
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "YOUR_MYSQL_PASSWORD",
    "database": "spotify_clone",
}
```

## 4. Run it
```bash
python app.py
```
Visit **https://early-terminal-chairman-consist.trycloudflare.com/**

Click on "Golden Hour", "Neon Dreams", "Static Bloom", "Concrete Verses",
"Blue Room", "Circuit Dreams", "Midnight Hours", "Open Road", "Firelight",
or "Sunset Drive" — these 10 have real short demo tracks and will actually
play, with working pause, seek, and volume. Every other song is real data
but has no audio behind it yet (fake `example.com` URL) — clicking those
just won't produce sound until you swap in a real file.

## About the demo audio
Since this environment couldn't reach external audio sites (Free Music
Archive, Pixabay, etc.), the 10 demo tracks were generated programmatically
(`generate_audio.py`, pure Python `wave` module — simple synthesized
melodies, ~5-7 seconds each). No copyright concerns, but they're tones,
not songs. To swap in real royalty-free music:
1. Download tracks from Free Music Archive, Pixabay Audio, or the
   YouTube Audio Library.
2. Drop the mp3/wav files into `static/audio/`.
3. `UPDATE Songs SET file_url = '/audio/yourfile.mp3' WHERE song_id = X;`

## What each feature maps to
- **Search** → `/api/search?q=` — SQL `LIKE` on song title + artist name
- **Recommendations** → `/api/songs/<id>/recommendations` — plain SQL:
  same `artist_id`, ordered by `play_count DESC`. No AI/ML involved.
- **Play/Pause** → handled entirely client-side via the HTML5 `<audio>`
  element in `static/js/app.js`
- **Volume** → `audio.volume`, tied to the slider in the player bar
- **Play tracking** → `POST /api/play/<id>` increments `play_count` and
  logs a row into `RecentlyPlayed`

## Next steps you might want
- User login (you already have a `Users` table + a demo user seeded)
- Playlist create/add/remove endpoints (table already exists: `Playlists`,
  `PlaylistSongs`)
- Genre filter using `SongGenre`
- Swap all 50 songs to real music instead of just the 10 demo ones
