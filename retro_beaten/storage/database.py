import sqlite3
from retro_beaten.library import normalize_name
from retro_beaten.statuses import STATUS_LABELS


def backup_before_wishlist(database_path):
    """Back up the old database before extending the allowed statuses."""
    if not database_path.exists():
        return
    source = sqlite3.connect(database_path)
    try:
        schema = source.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
        ).fetchone()
        backup_path = database_path.with_name(f"{database_path.stem}.before_wishlist.db")
        if schema and "'wishlist'" not in schema[0] and not backup_path.exists():
            destination = sqlite3.connect(backup_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
    finally:
        source.close()


def initialize_database(database_path):
    """Create the database folder and games table if needed."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    backup_before_wishlist(database_path)

    connection = sqlite3.connect(database_path, autocommit=False)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                cover_path TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'beaten'
                    CHECK (status IN ('playing', 'beaten', 'dropped', 'wishlist'))
            )
        """)
        # Upgrade old databases without deleting existing games.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(games)")}
        if "igdb_id" not in columns:
            connection.execute("ALTER TABLE games ADD COLUMN igdb_id INTEGER")
        if "summary" not in columns:
            connection.execute("ALTER TABLE games ADD COLUMN summary TEXT NOT NULL DEFAULT ''")
        # SQLite requires rebuilding the table to extend a CHECK constraint.
        # Copy and swap in one transaction, preserving all IDs.
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'games'"
        ).fetchone()[0]
        if "'wishlist'" not in schema:
            connection.execute("""
                CREATE TABLE games_with_wishlist (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    cover_path TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'beaten'
                        CHECK (status IN ('playing', 'beaten', 'dropped', 'wishlist')),
                    igdb_id INTEGER,
                    summary TEXT NOT NULL DEFAULT ''
                )
            """)
            connection.execute("""
                INSERT INTO games_with_wishlist
                SELECT id, name, platform, cover_path, status, igdb_id, summary FROM games
            """)
            connection.execute("DROP TABLE games")
            connection.execute("ALTER TABLE games_with_wishlist RENAME TO games")
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS games_igdb_platform
            ON games (igdb_id, platform)
        """)
        connection.commit()
    finally:
        connection.close()

def import_games(database_path, games, project_dir):
    """Insert new games without changing existing records."""
    connection = sqlite3.connect(database_path, autocommit=False)

    try:
        for game in games:
            relative_path = game["cover_path"].relative_to(project_dir)

            connection.execute("""
                INSERT INTO games (name, platform, cover_path, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cover_path) DO NOTHING
            """, (
                game["name"],
                game["platform"],
                relative_path.as_posix(),
                game["status"]
            ))

        connection.commit()
    finally:
        connection.close()

def load_saved_games(database_path, project_dir):
    """Read games from the database and resolve cover paths."""
    connection = sqlite3.connect(database_path, autocommit=False)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute("""
            SELECT id, name, platform, cover_path, status, igdb_id, summary
            FROM games
            ORDER BY name
        """).fetchall()

        games = []

        for row in rows:
            game = dict(row)
            game["cover_path"] = project_dir / game["cover_path"]
            games.append(game)

        return games
    finally:
        connection.close()


def has_igdb_game(database_path, igdb_id, platform):
    """Check whether this game version is already in the collection."""
    connection = sqlite3.connect(database_path)
    try:
        return connection.execute(
            "SELECT 1 FROM games WHERE igdb_id = ? AND platform = ?",
            (igdb_id, platform)
        ).fetchone() is not None
    finally:
        connection.close()


def insert_igdb_game(database_path, game):
    """Save a game record and return its local ID."""
    connection = sqlite3.connect(database_path, autocommit=False)
    try:
        cursor = connection.execute("""
            INSERT INTO games (name, platform, cover_path, status, igdb_id, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(igdb_id, platform) DO NOTHING
        """, (
            game["name"], game["platform"], game["cover_path"],
            game["status"], game["igdb_id"], game["summary"]
        ))
        if cursor.rowcount != 1:
            raise ValueError("This game is already in your collection for this platform.")
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()

def update_game_status(database_path, game_id, new_status):
    """Update a game's status using its ID."""
    if new_status not in STATUS_LABELS:
        raise ValueError(f"Invalid status: {new_status}")

    connection = sqlite3.connect(database_path, autocommit=False)

    try:
        cursor = connection.execute("""
            UPDATE games
            SET status = ?
            WHERE id = ?
        """, (new_status, game_id))

        if cursor.rowcount != 1:
            raise ValueError(f"Game not found: {game_id}")

        connection.commit()
    finally:
        connection.close()


def insert_manual_game(database_path, game):
    """Save a local record without an IGDB ID."""
    connection = sqlite3.connect(database_path, autocommit=False)
    try:
        existing = connection.execute(
            "SELECT name FROM games WHERE platform = ?", (game["platform"],)
        ).fetchall()
        if any(normalize_name(row[0]) == normalize_name(game["name"]) for row in existing):
            raise ValueError("A game with this name already exists on this platform.")
        cursor = connection.execute("""
            INSERT INTO games (name, platform, cover_path, status, igdb_id, summary)
            VALUES (?, ?, ?, ?, NULL, ?)
        """, (
            game["name"], game["platform"], game["cover_path"],
            game["status"], game["summary"]
        ))
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def update_game_details(database_path, game_id, name, summary):
    """Save name and description together while preserving other fields."""
    connection = sqlite3.connect(database_path, autocommit=False)
    try:
        row = connection.execute(
            "SELECT name, platform FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if row is None:
            raise ValueError("This game is no longer in your collection.")
        # Different IGDB records may share a title. Editing only
        # their description remains allowed.
        if normalize_name(name) != normalize_name(row[0]):
            existing = connection.execute(
                "SELECT name FROM games WHERE platform = ? AND id != ?", (row[1], game_id)
            ).fetchall()
            if any(normalize_name(other[0]) == normalize_name(name) for other in existing):
                raise ValueError("A game with this name already exists on this platform.")
        connection.execute(
            "UPDATE games SET name = ?, summary = ? WHERE id = ?", (name, summary, game_id)
        )
        connection.commit()
    finally:
        connection.close()


def update_game_cover(database_path, game_id, cover_path):
    """Update only the cover and return the previous path after committing."""
    connection = sqlite3.connect(database_path, autocommit=False)
    try:
        row = connection.execute("SELECT cover_path FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            raise ValueError("This game is no longer in your collection.")
        connection.execute("UPDATE games SET cover_path = ? WHERE id = ?", (cover_path, game_id))
        connection.commit()
        return row[0]
    finally:
        connection.close()


def delete_saved_game(database_path, game_id):
    """Delete only the requested record and return its cover path after committing."""
    connection = sqlite3.connect(database_path, autocommit=False)
    try:
        row = connection.execute("SELECT cover_path FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            raise ValueError("This game is no longer in your collection.")
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        connection.commit()
        return row[0]
    finally:
        connection.close()
