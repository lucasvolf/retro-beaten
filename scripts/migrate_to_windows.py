"""Copy a development collection to the executable's persistent data folder."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from retro_beaten.paths import PROJECT_DIR, user_data_dir
from retro_beaten.services.backup import create_backup, prepare_backup, replace_records
from retro_beaten.services.recommendations import load_recommendations, save_recommendations
from retro_beaten.storage.database import initialize_database, load_saved_games


def migrate(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    # Never replace an executable collection that is already in use.
    if destination.exists():
        raise ValueError("The destination folder already exists. Use Backup and restore in the app to replace the collection.")
    if not (source / "data/retro_beaten.db").is_file():
        raise ValueError("The source project does not contain a collection.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="retro-beaten-migration-", dir=destination.parent) as temporary:
        work = Path(temporary)
        backup = work / "collection.zip"
        count = create_backup(source / "data/retro_beaten.db", source, backup)
        staging = work / "prepared"
        images = staging / "assets/images"
        images.mkdir(parents=True)
        records = prepare_backup(backup, images)
        database = staging / "data/retro_beaten.db"
        initialize_database(database)
        replace_records(database, records)
        # Keep the initial backup available for restoration through the application.
        (staging / "backups").mkdir()
        shutil.copyfile(backup, staging / "backups/collection-before-executable.zip")
        collection = load_saved_games(source / "data/retro_beaten.db", source)
        recommendations = load_recommendations(source, collection)
        for game in recommendations:
            target = staging / "assets/recommendations" / game["cover_path"].name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(game["cover_path"], target)
            game["cover_path"] = target
        save_recommendations(staging, recommendations)
        # Copy secrets locally without printing or including them in the distribution.
        if (source / ".env").is_file():
            shutil.copyfile(source / ".env", staging / ".env")
        staging.rename(destination)
    return count


if __name__ == "__main__":
    target = user_data_dir()
    count = migrate(PROJECT_DIR, target)
    print(f"Collection copied: {count} games. Destination: {target}")
    print("The original collection was preserved.")
