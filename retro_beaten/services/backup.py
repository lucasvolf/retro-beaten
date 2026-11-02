"""Portable collection backups with validation before restoration."""

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from PIL import Image

from retro_beaten.library import normalize_name
from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS
from retro_beaten.storage.database import load_saved_games


FORMAT_VERSION = 2
MAX_GAMES = 10000
MAX_MANIFEST_BYTES = 20 * 1024 * 1024
MAX_COVER_BYTES = 50 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def image_extension(data):
    """Validate cover contents rather than trusting the file extension."""
    try:
        with Image.open(BytesIO(data)) as image:
            extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(image.format)
            if extension is None:
                raise ValueError("The backup contains a cover in an unsupported format.")
            image.load()
            return extension
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("One of the covers is invalid or damaged.") from error


def validate_records(records):
    """Accept only fields and values supported by the collection."""
    if not isinstance(records, list) or len(records) > MAX_GAMES:
        raise ValueError("The game list is invalid or too large.")
    ids, igdb_versions = set(), set()
    fields = {"id", "name", "platform", "status", "summary", "igdb_id", "cover_path", "sha256", "favorite"}
    for game in records:
        if not isinstance(game, dict) or set(game) != fields:
            raise ValueError("A backup record is incomplete or invalid.")
        if type(game["favorite"]) is not bool:
            raise ValueError("Invalid favorite flag.")
        identifier = game["id"]
        if type(identifier) is not int or identifier <= 0 or identifier > 2**63 - 1 or identifier in ids:
            raise ValueError("Invalid or duplicate game ID.")
        ids.add(identifier)
        if not isinstance(game["name"], str) or not normalize_name(game["name"]):
            raise ValueError("A game in the backup does not have a valid name.")
        if not isinstance(game["summary"], str):
            raise ValueError("Invalid game description.")
        if not isinstance(game["platform"], str) or game["platform"] not in PLATFORMS:
            raise ValueError("The backup contains an unknown platform.")
        if not isinstance(game["status"], str) or game["status"] not in STATUS_LABELS:
            raise ValueError("The backup contains an unknown status.")
        igdb_id = game["igdb_id"]
        if igdb_id is not None:
            if type(igdb_id) is not int or not 0 < igdb_id <= 2**63 - 1:
                raise ValueError("Invalid IGDB ID.")
            version = (igdb_id, game["platform"])
            if version in igdb_versions:
                raise ValueError("The backup contains duplicate IGDB records.")
            igdb_versions.add(version)
        if game["cover_path"] not in [f"covers/{identifier}.{ext}" for ext in ("jpg", "png", "webp")]:
            raise ValueError("Invalid cover path in the backup.")
        digest = game["sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid cover integrity checksum.")


def create_backup(database_path, project_dir, destination):
    """Export records and covers; publish the ZIP only after it is complete."""
    project_dir, destination = Path(project_dir).resolve(), Path(destination).resolve()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Choose a file with the .zip extension.")
    if any(destination.is_relative_to(project_dir / folder) for folder in ("assets", "data")):
        raise ValueError("Save the backup outside the assets and data folders.")
    # A single SQLite read provides a consistent snapshot of collection records.
    games = load_saved_games(database_path, project_dir)
    if len(games) > MAX_GAMES:
        raise ValueError("The collection exceeds the limit of 10,000 games per backup.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
        records, total_size = [], 0
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED) as archive:
            for game in games:
                path = game["cover_path"]
                if not path.is_file():
                    raise ValueError(f"Cover not found for {game['name']}. Replace the cover and try again.")
                if path.stat().st_size > MAX_COVER_BYTES:
                    raise ValueError(f"The cover for {game['name']} exceeds 50 MB.")
                data = path.read_bytes()
                total_size += len(data)
                if len(data) > MAX_COVER_BYTES or total_size > MAX_TOTAL_BYTES:
                    raise ValueError("The covers exceed the backup size limit.")
                extension = image_extension(data)
                member = f"covers/{game['id']}.{extension}"
                records.append({**game, "cover_path": member, "sha256": sha256(data).hexdigest()})
                archive.writestr(member, data)
            validate_records(records)
            manifest = json.dumps({
                "app": "Retro Beaten", "version": FORMAT_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(), "games": records,
            }, ensure_ascii=False).encode("utf-8")
            if len(manifest) > MAX_MANIFEST_BYTES or total_size + len(manifest) > MAX_TOTAL_BYTES:
                raise ValueError("The data exceeds the backup size limit.")
            archive.writestr("collection.json", manifest)
        temporary.replace(destination)
        return len(records)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_backup(source, staging):
    """Validate in a temporary folder without extracting paths supplied by the ZIP."""
    try:
        with ZipFile(source) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (len(entries) > MAX_GAMES + 1 or len(names) != len(set(names))
                    or "collection.json" not in names
                    or sum(entry.file_size for entry in entries) > MAX_TOTAL_BYTES):
                raise ValueError("Invalid backup structure or size.")
            if archive.getinfo("collection.json").file_size > MAX_MANIFEST_BYTES:
                raise ValueError("The backup game list is too large.")
            manifest = json.loads(archive.read("collection.json"))
            if (not isinstance(manifest, dict) or manifest.get("app") != "Retro Beaten"
                    or type(manifest.get("version")) is not int or manifest["version"] not in (1, FORMAT_VERSION)):
                raise ValueError("This file is not a compatible Retro Beaten backup.")
            records = manifest.get("games")
            if manifest["version"] == 1 and isinstance(records, list):
                records = [{**game, "favorite": False} if isinstance(game, dict) and "favorite" not in game else game
                           for game in records]
            validate_records(records)
            if set(names) != {"collection.json", *(game["cover_path"] for game in records)}:
                raise ValueError("The backup contains unexpected files or missing covers.")
            prepared = []
            for game in records:
                member = game["cover_path"]
                if archive.getinfo(member).file_size > MAX_COVER_BYTES:
                    raise ValueError("A cover in the backup exceeds 50 MB.")
                data = archive.read(member)
                if sha256(data).hexdigest() != game["sha256"]:
                    raise ValueError(f"The cover for {game['name']} is damaged or has been modified.")
                extension = image_extension(data)
                filename = f"{game['platform']}_{uuid4().hex}.{extension}"
                (staging / filename).write_bytes(data)
                prepared.append({**game, "cover_path": f"assets/images/{filename}"})
            return prepared
    except (BadZipFile, UnicodeError, json.JSONDecodeError, RuntimeError, NotImplementedError) as error:
        raise ValueError("Could not read the backup. The ZIP is invalid, damaged or protected.") from error


def replace_records(database_path, records):
    """Replace the entire collection in a transaction or keep every previous record."""
    with closing(sqlite3.connect(database_path, autocommit=False)) as connection:
        connection.execute("DELETE FROM games")
        connection.executemany("""
            INSERT INTO games (id, name, platform, cover_path, status, igdb_id, summary, favorite)
            VALUES (:id, :name, :platform, :cover_path, :status, :igdb_id, :summary, :favorite)
        """, records)
        connection.commit()


def restore_backup(database_path, project_dir, source):
    """Validate and back up the previous collection before committing the replacement."""
    project_dir = Path(project_dir).resolve()
    with TemporaryDirectory(prefix="retro-beaten-restore-") as folder:
        staging = Path(folder)
        records = prepare_backup(source, staging)
        backup_name = f"before-restore-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.zip"
        safety_backup = project_dir / "backups" / backup_name
        create_backup(database_path, project_dir, safety_backup)
        covers_dir = project_dir / "assets/images"
        covers_dir.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            for game in records:
                target = project_dir / game["cover_path"]
                # Exclusive creation never overwrites an existing cover.
                with target.open("xb") as output:
                    created.append(target)
                    output.write((staging / target.name).read_bytes())
            replace_records(database_path, records)
        except Exception:
            for path in created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass  # An unreferenced file does not compromise the previous collection.
            raise
        # Keep old covers; restoration does not delete personal files.
        return {"count": len(records), "safety_backup": safety_backup}
