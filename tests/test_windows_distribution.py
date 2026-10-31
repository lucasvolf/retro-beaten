"""Executable paths and migration without touching personal data."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from retro_beaten.paths import get_data_dir, PROJECT_DIR
from retro_beaten.services.collection import register_manual_game
from retro_beaten.services.igdb_api import load_credentials
from retro_beaten.storage.database import initialize_database, load_saved_games
from scripts.migrate_to_windows import migrate


class DistributionTests(unittest.TestCase):
    def test_frozen_data_and_credentials_live_outside_bundle(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict(os.environ, {"LOCALAPPDATA": folder, "IGDB_CLIENT_ID": "test", "IGDB_CLIENT_SECRET": "test"}), \
             patch("sys.frozen", True, create=True), \
             patch("retro_beaten.services.igdb_api.load_dotenv") as dotenv:
            target = Path(folder) / "RetroBeaten"
            self.assertEqual(get_data_dir(), target)
            load_credentials()
            self.assertEqual(dotenv.call_args.args[0], target / ".env")

    def test_development_keeps_project_collection(self):
        with patch("sys.frozen", False, create=True):
            self.assertEqual(get_data_dir(), PROJECT_DIR)

    def test_migration_preserves_source_and_does_not_overwrite_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder) / "project", Path(folder) / "user-data"
            database = source / "data/retro_beaten.db"
            initialize_database(database)
            cover = source / "cover.png"
            Image.new("RGB", (30, 40), "navy").save(cover)
            record = register_manual_game(database, source, "Game", "PS2", "playing", cover, "Description")
            (source / ".env").write_text("FAKE_TEST_SECRET=local-only")
            self.assertEqual(migrate(source, destination), 1)
            self.assertEqual(load_saved_games(database, source), [record])
            restored = load_saved_games(destination / "data/retro_beaten.db", destination)[0]
            self.assertEqual(restored["name"], record["name"])
            self.assertEqual(restored["status"], "playing")
            self.assertEqual(restored["cover_path"].read_bytes(), cover.read_bytes())
            self.assertTrue(restored["cover_path"].is_relative_to(destination))
            self.assertEqual((destination / ".env").read_bytes(), (source / ".env").read_bytes())
            self.assertTrue((destination / "backups/collection-before-executable.zip").exists())
            with self.assertRaises(ValueError):
                migrate(source, destination)

    def test_failed_migration_does_not_publish_partial_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            source, destination = Path(folder) / "project", Path(folder) / "user-data"
            database = source / "data/retro_beaten.db"
            initialize_database(database)
            with patch("scripts.migrate_to_windows.replace_records", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    migrate(source, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(load_saved_games(database, source), [])
            self.assertEqual(list(Path(folder).iterdir()), [source])
