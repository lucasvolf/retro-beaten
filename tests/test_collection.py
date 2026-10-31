"""Registration tests with databases and covers isolated from the personal collection."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from retro_beaten.services.collection import register_game
from retro_beaten.storage.database import initialize_database, load_saved_games, update_game_status


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data" / "test.db"
        initialize_database(self.db)
        self.preview = self.project / "preview.jpg"
        Image.new("RGB", (300, 400), "navy").save(self.preview)
        self.game = {
            "id": 306134, "name": "Tekken 3", "summary": "Test description",
            "platforms": [{"id": 7, "name": "PlayStation"}, {"id": 8, "name": "PlayStation 2"}]
        }

    def register(self, platform="PS1", status="playing"):
        return register_game(self.db, self.project, self.game, platform, status, self.preview)

    def test_persists_metadata_status_and_local_cover(self):
        record = self.register()
        games = load_saved_games(self.db, self.project)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0], record)
        self.assertEqual(games[0]["summary"], "Test description")
        self.assertEqual(games[0]["cover_path"].read_bytes(), self.preview.read_bytes())
        with closing(sqlite3.connect(self.db)) as connection:
            stored_path = connection.execute("SELECT cover_path FROM games").fetchone()[0]
        self.assertFalse(Path(stored_path).is_absolute())
        update_game_status(self.db, record["id"], "dropped")
        self.assertEqual(load_saved_games(self.db, self.project)[0]["status"], "dropped")

    def test_duplicate_does_not_change_status_or_leave_another_cover(self):
        self.register()
        with self.assertRaisesRegex(ValueError, "already in your collection"):
            self.register(status="beaten")
        games = load_saved_games(self.db, self.project)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["status"], "playing")
        self.assertEqual(len(list((self.project / "assets" / "images").iterdir())), 1)

    def test_same_igdb_game_can_have_two_consoles_and_independent_covers(self):
        first = self.register("PS1")
        second = self.register("PS2", "beaten")
        self.assertEqual(len(load_saved_games(self.db, self.project)), 2)
        self.assertNotEqual(first["cover_path"], second["cover_path"])
        self.assertNotEqual(first["id"], second["id"])

    def test_wrong_console_or_status_is_not_saved(self):
        for platform, status in [("GBA", "beaten"), ("PS1", "unknown")]:
            with self.assertRaises(ValueError):
                self.register(platform, status)
        self.assertEqual(load_saved_games(self.db, self.project), [])
        self.assertFalse((self.project / "assets" / "images").exists())

    def test_database_failure_removes_only_new_copy(self):
        existing = self.register()
        with patch("retro_beaten.services.collection.insert_igdb_game", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                self.register("PS2")
        self.assertEqual(list((self.project / "assets" / "images").iterdir()), [existing["cover_path"]])
        self.assertTrue(self.preview.exists())
        self.assertEqual(len(load_saved_games(self.db, self.project)), 1)

    def test_invalid_cover_is_not_saved(self):
        self.preview = self.project / "invalid.jpg"
        self.preview.write_bytes(b"not an image")
        with self.assertRaises(OSError):
            self.register()
        self.assertEqual(load_saved_games(self.db, self.project), [])

    def test_duplicate_is_enforced_by_database_too(self):
        self.register()
        with patch("retro_beaten.services.collection.has_igdb_game", return_value=False):
            with self.assertRaisesRegex(ValueError, "already in your collection"):
                self.register()
        self.assertEqual(len(list((self.project / "assets" / "images").iterdir())), 1)

    def test_pc_game_can_be_registered_and_loaded(self):
        self.game = {
            "id": 999, "name": "PC game", "summary": "Local description",
            "platforms": [{"id": 6, "name": "PC (Microsoft Windows)"}]
        }
        record = self.register("PC", "beaten")
        self.assertEqual(load_saved_games(self.db, self.project), [record])


class MigrationTests(unittest.TestCase):
    def test_old_database_keeps_records_and_can_be_initialized_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            db = project / "old.db"
            with closing(sqlite3.connect(db)) as connection:
                connection.execute("""CREATE TABLE games (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL,
                    cover_path TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'beaten'
                )""")
                connection.execute("INSERT INTO games VALUES (1, 'Old game', 'PS1', 'assets/images/old.jpg', 'dropped')")
                connection.commit()
            initialize_database(db)
            initialize_database(db)
            games = load_saved_games(db, project)
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]["status"], "dropped")
            self.assertIsNone(games[0]["igdb_id"])
            self.assertEqual(games[0]["summary"], "")


if __name__ == "__main__":
    unittest.main()
