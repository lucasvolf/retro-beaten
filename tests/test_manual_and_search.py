"""Manual registration and local search using temporary data only."""

import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten.services.collection import register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.library import filter_games
from retro_beaten.ui.library_search import LibrarySearch
from retro_beaten.ui.library_view import render_library
from retro_beaten.ui.manual_game_window import ManualGameWindow


class FilterTests(unittest.TestCase):
    def test_search_preserves_collection_and_ignores_accents_spaces_and_case(self):
        games = [
            {"name": "HuniePop", "status": "playing"},
            {"name": "To the Moon", "status": "beaten"},
            {"name": "Pokémon", "status": "dropped"}
        ]
        self.assertEqual(filter_games(games, " HUNIE pop "), [games[0]])
        self.assertEqual(filter_games(games, "moon"), [games[1]])
        self.assertEqual(filter_games(games, "pokemon"), [games[2]])
        self.assertEqual(filter_games(games, "missing"), [])
        self.assertEqual(filter_games(games, ""), games)
        self.assertEqual(len(games), 3)
        self.assertIs(filter_games(games, "moon")[0], games[1])


class ManualRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data/test.db"
        initialize_database(self.db)
        self.source = self.project / "original.png"
        # Small synthetic image: this test does not depend on collection covers.
        Image.new("RGB", (6, 8), "navy").save(self.source)

    def register(self, name="To the Moon", platform="PC"):
        return register_manual_game(
            self.db, self.project, name, platform, "beaten", self.source, "Personal description"
        )

    def test_four_manual_games_persist_without_network_or_igdb_ids(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("Manual registration is offline")):
            for name in ("How to Fish", "Hunie Pop", "Mirror", "To the Moon"):
                self.register(name)
        self.source.unlink()
        games = load_saved_games(self.db, self.project)
        self.assertEqual(len(games), 4)
        for game in games:
            self.assertIsNone(game["igdb_id"])
            self.assertEqual(game["platform"], "PC")
            self.assertEqual(game["summary"], "Personal description")
            self.assertTrue(game["cover_path"].is_file())
            self.assertEqual(game["cover_path"].suffix, ".png")

    def test_duplicate_normalized_name_is_blocked_but_other_platform_allowed(self):
        self.register("HuniePop")
        with self.assertRaises(ValueError):
            self.register(" HUNIE POP ")
        self.assertEqual(len(list((self.project / "assets/images").iterdir())), 1)
        self.register("HuniePop", "PS1")
        self.assertEqual(len(load_saved_games(self.db, self.project)), 2)

    def test_failed_insert_cleans_copy_and_keeps_original(self):
        with patch("retro_beaten.services.collection.insert_manual_game", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.OperationalError):
                self.register()
        self.assertTrue(self.source.exists())
        self.assertEqual(list((self.project / "assets/images").iterdir()), [])
        self.assertEqual(load_saved_games(self.db, self.project), [])

    def test_missing_name_cover_and_invalid_image_are_rejected(self):
        for name, cover in [("  ", self.source), ("Game", None)]:
            with self.assertRaises(ValueError):
                register_manual_game(self.db, self.project, name, "PC", "beaten", cover)
        self.source.write_bytes(b"invalid")
        with self.assertRaises(OSError):
            self.register()
        self.assertEqual(load_saved_games(self.db, self.project), [])

    def test_jpeg_and_webp_keep_the_original_bytes(self):
        for format_name, extension in [("JPEG", ".jpg"), ("WEBP", ".webp")]:
            self.source = self.project / f"cover{extension}"
            Image.new("RGB", (6, 8), "navy").save(self.source, format=format_name)
            record = self.register(format_name)
            self.assertEqual(record["cover_path"].suffix, extension)
            self.assertEqual(record["cover_path"].read_bytes(), self.source.read_bytes())


class ManualAndSearchWindowTests(unittest.TestCase):
    def test_manual_form_and_local_search(self):
        root = ctk.CTk()
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            with tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                db = project / "data/test.db"
                initialize_database(db)
                source = project / "cover.png"
                Image.new("RGB", (6, 8), "navy").save(source)
                games = []
                panel = ctk.CTkFrame(root)
                filters = []

                def refresh():
                    filters.append(search.get_query())
                    for child in panel.winfo_children():
                        child.destroy()
                    render_library(panel, games, lambda *args: None, lambda game: None, search.get_query())

                search = LibrarySearch(root, refresh)

                def add(name, platform, status, cover, summary):
                    games.append(register_manual_game(db, project, name, platform, status, cover, summary))
                    search.clear()
                    refresh()

                window = ManualGameWindow(root, add)
                window.withdraw()
                window.save_game()
                self.assertEqual(games, [])
                window.name_entry.insert(0, "To the Moon")
                window.save_game()
                self.assertEqual(games, [])
                window.load_cover(source)
                # Changing the image and cancelling the picker preserves the valid preview.
                window.load_cover(source)
                with patch("retro_beaten.ui.manual_game_window.filedialog.askopenfilename", return_value=""):
                    window.choose_cover()
                self.assertEqual(window.cover_path, source)
                window.status_menu.set("Playing")
                window.summary_box.insert("1.0", "My description")
                search.query.set("outra busca")
                window.save_game()
                self.assertFalse(window.winfo_exists())
                self.assertEqual(search.get_query(), "")
                self.assertEqual(games[0]["status"], "playing")
                self.assertIsNone(games[0]["igdb_id"])

                search.query.set("m")
                search.query.set("MOON")
                end = time.monotonic() + 0.4
                while time.monotonic() < end:
                    root.update()
                    time.sleep(0.02)
                self.assertEqual(filters[-1], "MOON")
                self.assertEqual(len(panel.winfo_children()), 1)
                search.query.set("does not exist")
                search.notify_change()
                message = panel.winfo_children()[0]
                self.assertIn("No games found", message.cget("text"))
                search.clear()
                search.notify_change()
                self.assertEqual(len(games), 1)
                self.assertEqual(len(load_saved_games(db, project)), 1)
                self.assertEqual(errors, [])
        finally:
            # Cancel GUI timers before shutting down Tk.
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
