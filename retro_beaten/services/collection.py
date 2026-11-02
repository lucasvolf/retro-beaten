"""Add IGDB or manually entered games to the local collection."""

from pathlib import Path
from io import BytesIO
from uuid import uuid4
import re
import sqlite3

from PIL import Image

from retro_beaten.storage.database import (
    has_igdb_game, insert_igdb_game, insert_manual_game,
    update_game_cover, delete_saved_game, load_saved_games, update_game_details,
)
from retro_beaten.library import normalize_name
from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS


def register_game(database_path, project_dir, game, platform, status, preview_path):
    """Copy the previewed cover and save the game with its platform and status."""
    if platform not in PLATFORMS:
        raise ValueError("Unknown platform.")
    if status not in STATUS_LABELS:
        raise ValueError("Unknown status.")
    igdb_id = int(game["id"])
    name = game.get("name", "").strip()
    if not name or igdb_id <= 0:
        raise ValueError("The game does not have a valid name or ID.")
    if not any(p["id"] == PLATFORMS[platform]["igdb_id"] for p in game.get("platforms", [])):
        raise ValueError("This game is not available on the selected platform.")
    if has_igdb_game(database_path, igdb_id, platform):
        raise ValueError("This game is already in your collection for this platform.")

    record = {
        "name": name, "platform": platform, "status": status,
        "favorite": False, "igdb_id": igdb_id, "summary": game.get("summary") or ""
    }
    return save_game_with_cover(database_path, project_dir, record, preview_path, insert_igdb_game)


def register_manual_game(database_path, project_dir, name, platform, status, cover_path, summary=""):
    """Validate the manual form and save a copy of the cover."""
    name = name.strip()
    if not normalize_name(name):
        raise ValueError("Enter a game name.")
    if platform not in PLATFORMS:
        raise ValueError("Unknown platform.")
    if status not in STATUS_LABELS:
        raise ValueError("Unknown status.")
    if not cover_path:
        raise ValueError("Choose a cover image.")
    record = {
        "name": name, "platform": platform, "status": status,
        "favorite": False, "igdb_id": None, "summary": summary.strip()
    }
    return save_game_with_cover(database_path, project_dir, record, cover_path, insert_manual_game)


def edit_game_details(database_path, game_id, name, summary):
    """Validate edits and return fields only after a successful save."""
    name = name.strip()
    if not normalize_name(name):
        raise ValueError("Enter a game name.")
    summary = summary.strip()
    update_game_details(database_path, game_id, name, summary)
    return {"name": name, "summary": summary}


def save_game_with_cover(database_path, project_dir, record, source_path, insert_record):
    """Share cover storage between both registration methods."""
    # Use the previewed bytes to avoid rereading a changed source file.
    image_data = source_path if isinstance(source_path, bytes) else Path(source_path).read_bytes()
    with Image.open(BytesIO(image_data)) as image:
        extensions = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
        if image.format not in extensions:
            raise ValueError("Choose a PNG, JPEG or WebP image.")
        extension = extensions[image.format]
        image.load()

    project_dir = Path(project_dir).resolve()
    covers_dir = project_dir / "assets" / "images"
    covers_dir.mkdir(parents=True, exist_ok=True)
    # A separate file per record allows independent cover changes for each version.
    cover_path = covers_dir / f"{record['platform']}_{uuid4().hex}{extension}"
    record["cover_path"] = cover_path.relative_to(project_dir).as_posix()
    try:
        cover_path.write_bytes(image_data)
        record["id"] = insert_record(database_path, record)
    except Exception:
        # If registration fails, remove only the copy created by this operation.
        cover_path.unlink(missing_ok=True)
        raise
    record["cover_path"] = cover_path
    return record


def replace_cover(database_path, project_dir, game, image_data):
    """Save the new copy before updating the database; keep the record on failure."""
    previous_paths = []

    def update_record(database_path, record):
        previous_paths.append(update_game_cover(database_path, game["id"], record["cover_path"]))
        return game["id"]

    record = save_game_with_cover(database_path, project_dir, dict(game), image_data, update_record)
    remove_unused_cover(database_path, project_dir, previous_paths[0])
    return record["cover_path"]


def delete_game(database_path, project_dir, game_id):
    """Delete the record and attempt to remove only its app-managed cover copy."""
    previous_path = delete_saved_game(database_path, game_id)
    remove_unused_cover(database_path, project_dir, previous_path)


def remove_unused_cover(database_path, project_dir, relative_path):
    """Never remove external originals, legacy covers, or images still referenced."""
    project_dir = Path(project_dir).resolve()
    path = project_dir / relative_path
    try:
        # Only owned files: platform_UUID.ext, directly inside assets/images.
        if (path.is_symlink() or path.resolve().parent != project_dir / "assets" / "images"
                or not re.fullmatch(r"[A-Z0-9]+_[0-9a-f]{32}\.(jpg|png|webp)", path.name)):
            return
        if any(game["cover_path"].resolve() == path.resolve()
               for game in load_saved_games(database_path, project_dir)):
            return
        path.unlink(missing_ok=True)
    except (OSError, sqlite3.Error):
        # The record is already saved. A locked file can be cleaned up later.
        pass
