"""
MiniBeat - Flask backend
Run: python app.py
Requires: pip install flask mysql-connector-python bcrypt
"""
from flask import Flask, jsonify, request, send_from_directory, render_template, session
import mysql.connector
from mysql.connector import pooling
import bcrypt

app = Flask(__name__)
app.secret_key = "change-this-to-something-random-in-production"

# ---------------------------------------------------------
# DB CONFIG -- edit these to match your local MySQL setup
# ---------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",       # <-- change to your MySQL username
    "password": "Harsha@123",   # <-- change to your MySQL password
    "database": "spotify_clone",
}

pool = pooling.MySQLConnectionPool(pool_name="spotify_pool", pool_size=5, **DB_CONFIG)


def get_conn():
    return pool.get_connection()


def query(sql, params=None, fetch=True):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    result = cur.fetchall() if fetch else None
    last_id = cur.lastrowid
    if not fetch:
        conn.commit()
    cur.close()
    conn.close()
    if fetch:
        return result
    return last_id


# ---------------------------------------------------------
# PAGE
# ---------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------
# AUTH
# ---------------------------------------------------------
def current_user_id():
    return session.get("user_id")


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify({"error": "username, email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    existing = query(
        "SELECT user_id FROM Users WHERE username = %s OR email = %s",
        (username, email),
    )
    if existing:
        return jsonify({"error": "username or email already taken"}), 409

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_id = query(
        "INSERT INTO Users (username, email, password) VALUES (%s, %s, %s)",
        (username, email, hashed),
        fetch=False,
    )
    session["user_id"] = new_id
    session["username"] = username
    return jsonify({"ok": True, "user_id": new_id, "username": username}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    rows = query("SELECT * FROM Users WHERE username = %s", (username,))
    if not rows:
        return jsonify({"error": "invalid username or password"}), 401

    user = rows[0]
    if not bcrypt.checkpw(password.encode(), user["password"].encode()):
        return jsonify({"error": "invalid username or password"}), 401

    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    return jsonify({"ok": True, "user_id": user["user_id"], "username": user["username"]})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/auth/me")
def me():
    if not current_user_id():
        return jsonify({"logged_in": False})
    if not query("SELECT user_id FROM Users WHERE user_id = %s", (current_user_id(),)):
        session.clear()
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user_id": session["user_id"], "username": session["username"]})


# ---------------------------------------------------------
# SONGS
# ---------------------------------------------------------
@app.route("/api/songs")
def list_songs():
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM Songs s
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        ORDER BY s.song_id
    """
    return jsonify(query(sql))


@app.route("/api/songs/<int:song_id>")
def get_song(song_id):
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM Songs s
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        WHERE s.song_id = %s
    """
    rows = query(sql, (song_id,))
    if not rows:
        return jsonify({"error": "not found"}), 404
    return jsonify(rows[0])


# ---------------------------------------------------------
# SEARCH  (songs by title OR artist name -- no AI, just SQL)
# ---------------------------------------------------------
@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM Songs s
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        WHERE s.title LIKE %s OR a.artist_name LIKE %s
        ORDER BY s.play_count DESC
    """
    return jsonify(query(sql, (like, like)))


# ---------------------------------------------------------
# RECOMMENDATIONS -- purely rule-based: same artist, most played first
# ---------------------------------------------------------
@app.route("/api/songs/<int:song_id>/recommendations")
def recommend(song_id):
    # find the artist of the given song
    artist_row = query("SELECT artist_id FROM Songs WHERE song_id = %s", (song_id,))
    if not artist_row:
        return jsonify({"error": "song not found"}), 404
    artist_id = artist_row[0]["artist_id"]

    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM Songs s
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        WHERE s.artist_id = %s AND s.song_id != %s
        ORDER BY s.play_count DESC
        LIMIT 10
    """
    return jsonify(query(sql, (artist_id, song_id)))


# ---------------------------------------------------------
# PLAY  -- increments play_count + logs RecentlyPlayed
# ---------------------------------------------------------
@app.route("/api/play/<int:song_id>", methods=["POST"])
def play_song(song_id):
    user_id = current_user_id()
    query("UPDATE Songs SET play_count = play_count + 1 WHERE song_id = %s", (song_id,), fetch=False)
    if user_id:
        query(
            "INSERT INTO RecentlyPlayed (user_id, song_id) VALUES (%s, %s)",
            (user_id, song_id),
            fetch=False,
        )
    return jsonify({"ok": True})


# ---------------------------------------------------------
# PLAYLISTS
# ---------------------------------------------------------
def owned_playlist(playlist_id, user_id):
    rows = query(
        "SELECT playlist_id, playlist_name FROM Playlists "
        "WHERE playlist_id = %s AND user_id = %s",
        (playlist_id, user_id),
    )
    return rows[0] if rows else None


@app.route("/api/playlists")
def list_playlists():
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    sql = """
        SELECT p.playlist_id, p.playlist_name, p.created_at,
               COUNT(ps.song_id) AS song_count
        FROM Playlists p
        LEFT JOIN PlaylistSongs ps ON p.playlist_id = ps.playlist_id
        WHERE p.user_id = %s
        GROUP BY p.playlist_id, p.playlist_name, p.created_at
        ORDER BY p.created_at DESC
    """
    return jsonify(query(sql, (user_id,)))


@app.route("/api/playlists", methods=["POST"])
def create_playlist():
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    if not query("SELECT user_id FROM Users WHERE user_id = %s", (user_id,)):
        app.logger.warning("Playlist creation rejected for stale session user_id=%s", user_id)
        session.clear()
        return jsonify({"error": "session expired; please log in again"}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("playlist_name") or "").strip()
    if not name:
        return jsonify({"error": "playlist_name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "playlist name must be 100 characters or fewer"}), 400
    try:
        new_id = query(
            "INSERT INTO Playlists (user_id, playlist_name) VALUES (%s, %s)",
            (user_id, name),
            fetch=False,
        )
    except mysql.connector.Error:
        app.logger.exception("Playlist creation failed for user_id=%s", user_id)
        return jsonify({"error": "playlist could not be created"}), 500
    return jsonify({"ok": True, "playlist_id": new_id, "playlist_name": name}), 201


@app.route("/api/playlists/<int:playlist_id>")
def get_playlist(playlist_id):
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    playlist = owned_playlist(playlist_id, user_id)
    if not playlist:
        return jsonify({"error": "playlist not found"}), 404
    return jsonify(playlist)


@app.route("/api/playlists/<int:playlist_id>", methods=["DELETE"])
def delete_playlist(playlist_id):
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    if not owned_playlist(playlist_id, user_id):
        return jsonify({"error": "playlist not found"}), 404
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM PlaylistSongs WHERE playlist_id = %s", (playlist_id,))
        cur.execute(
            "DELETE FROM Playlists WHERE playlist_id = %s AND user_id = %s",
            (playlist_id, user_id),
        )
        conn.commit()
    except mysql.connector.Error:
        conn.rollback()
        return jsonify({"error": "playlist could not be deleted"}), 500
    finally:
        cur.close()
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/playlists/<int:playlist_id>/songs")
def playlist_songs(playlist_id):
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    if not owned_playlist(playlist_id, user_id):
        return jsonify({"error": "playlist not found"}), 404
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url,
               ps.added_at
        FROM PlaylistSongs ps
        JOIN Songs s ON ps.song_id = s.song_id
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        WHERE ps.playlist_id = %s
        ORDER BY ps.added_at DESC
    """
    return jsonify(query(sql, (playlist_id,)))


@app.route("/api/playlists/<int:playlist_id>/songs", methods=["POST"])
def add_song_to_playlist(playlist_id):
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    if not owned_playlist(playlist_id, user_id):
        return jsonify({"error": "playlist not found"}), 404
    data = request.get_json(silent=True) or {}
    song_id = data.get("song_id")
    if isinstance(song_id, bool) or not isinstance(song_id, int) or song_id <= 0:
        return jsonify({"error": "song_id must be a positive integer"}), 400
    if not query("SELECT song_id FROM Songs WHERE song_id = %s", (song_id,)):
        return jsonify({"error": "song not found"}), 404
    try:
        query(
            "INSERT INTO PlaylistSongs (playlist_id, song_id) VALUES (%s, %s)",
            (playlist_id, song_id),
            fetch=False,
        )
    except mysql.connector.errors.IntegrityError:
        return jsonify({"error": "song already in playlist"}), 409
    except mysql.connector.Error:
        return jsonify({"error": "song could not be added"}), 500
    return jsonify({"ok": True}), 201


@app.route("/api/playlists/<int:playlist_id>/songs/<int:song_id>", methods=["DELETE"])
def remove_song_from_playlist(playlist_id, song_id):
    user_id = current_user_id()
    if not user_id:
        return jsonify({"error": "login required"}), 401
    if not owned_playlist(playlist_id, user_id):
        return jsonify({"error": "playlist not found"}), 404
    if not query(
        "SELECT playlist_id FROM PlaylistSongs WHERE playlist_id = %s AND song_id = %s",
        (playlist_id, song_id),
    ):
        return jsonify({"error": "song is not in playlist"}), 404
    query(
        "DELETE FROM PlaylistSongs WHERE playlist_id = %s AND song_id = %s",
        (playlist_id, song_id),
        fetch=False,
    )
    return jsonify({"ok": True})


# ---------------------------------------------------------
# GENRES
# ---------------------------------------------------------
@app.route("/api/genres")
def list_genres():
    sql = """
        SELECT g.genre_id, g.genre_name, COUNT(sg.song_id) AS song_count
        FROM Genres g
        LEFT JOIN SongGenre sg ON g.genre_id = sg.genre_id
        GROUP BY g.genre_id, g.genre_name
        ORDER BY g.genre_name
    """
    return jsonify(query(sql))


@app.route("/api/genres/<int:genre_id>/songs")
def genre_songs(genre_id):
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               a.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM SongGenre sg
        JOIN Songs s ON sg.song_id = s.song_id
        JOIN Artists a ON s.artist_id = a.artist_id
        LEFT JOIN Albums al ON s.album_id = al.album_id
        WHERE sg.genre_id = %s
        ORDER BY s.play_count DESC
    """
    return jsonify(query(sql, (genre_id,)))


# ---------------------------------------------------------
# ALBUMS
# ---------------------------------------------------------
@app.route("/api/albums")
def list_albums():
    sql = """
        SELECT al.album_id, al.album_title, al.release_year, al.cover_url,
               a.artist_id, a.artist_name
        FROM Albums al
        JOIN Artists a ON al.artist_id = a.artist_id
        ORDER BY al.album_title
    """
    return jsonify(query(sql))


@app.route("/api/albums/<int:album_id>/songs")
def album_songs(album_id):
    # songs grouped by each song's own artist (usually == album artist,
    # but this stays correct even for compilation-style albums)
    sql = """
        SELECT s.song_id, s.title, s.duration_sec, s.file_url, s.play_count,
               s.artist_id, a.artist_name,
               al.album_title, al.cover_url
        FROM Songs s
        JOIN Artists a ON s.artist_id = a.artist_id
        JOIN Albums al ON s.album_id = al.album_id
        WHERE s.album_id = %s
        ORDER BY a.artist_name, s.title
    """
    return jsonify(query(sql, (album_id,)))


# ---------------------------------------------------------
# ARTISTS
# ---------------------------------------------------------
@app.route("/api/artists")
def list_artists():
    return jsonify(query("SELECT * FROM Artists ORDER BY artist_name"))


# ---------------------------------------------------------
# STATIC AUDIO FILES
# ---------------------------------------------------------
@app.route("/audio/<path:filename>")
def serve_audio(filename):
    return send_from_directory("static/audio", filename)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
