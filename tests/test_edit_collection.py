"""Cover replacement and deletion with isolated test data."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten import app as application
from retro_beaten.services.collection import register_manual_game, replace_cover, delete_game
from retro_beaten.ui.cover_window import CoverWindow
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.ui.details_window import DetailsWindow
from retro_beaten.ui.library_view import render_library


class EditCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data/retro_beaten.db"
        initialize_database(self.db)
        self.original = self.project / "original.png"
        Image.new("RGB", (30, 40), "navy").save(self.original)
        self.game = register_manual_game(self.db, self.project, "My game", "PS1", "wishlist",
                                         self.original, "Personal description")
        self.other = register_manual_game(self.db, self.project, "My game", "PS2", "beaten",
                                          self.original, "Another platform")
        self.new_image = self.project / "new.jpg"
        Image.new("RGB", (80, 60), "gold").save(self.new_image)

    def test_replace_persists_cover_and_preserves_metadata_other_game_and_original(self):
        path = replace_cover(self.db, self.project, self.game, self.new_image.read_bytes())
        games = {g["id"]: g for g in load_saved_games(self.db, self.project)}
        self.assertEqual(games[self.game["id"]], {**self.game, "cover_path": path})
        self.assertEqual(games[self.other["id"]], self.other)
        self.assertEqual(path.read_bytes(), self.new_image.read_bytes())
        self.assertEqual(path.suffix, ".jpg")
        self.assertFalse(self.game["cover_path"].exists())
        self.assertTrue(self.original.is_file())
        self.assertTrue(self.other["cover_path"].is_file())
        with closing(sqlite3.connect(self.db)) as connection:
            stored = connection.execute("SELECT cover_path FROM games WHERE id=?", (self.game["id"],)).fetchone()[0]
        self.assertFalse(Path(stored).is_absolute())

    def test_invalid_or_truncated_image_does_not_change_database_or_covers(self):
        before = load_saved_games(self.db, self.project)
        covers = set((self.project / "assets/images").iterdir())
        for data in (b"not an image", self.original.read_bytes()[:40]):
            with self.assertRaises((OSError, ValueError)):
                replace_cover(self.db, self.project, self.game, data)
        self.assertEqual(load_saved_games(self.db, self.project), before)
        self.assertEqual(set((self.project / "assets/images").iterdir()), covers)

    def test_database_failure_removes_only_new_copy(self):
        with patch("retro_beaten.services.collection.update_game_cover", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.Error):
                replace_cover(self.db, self.project, self.game, self.new_image.read_bytes())
        self.assertEqual(len(list((self.project / "assets/images").iterdir())), 2)
        self.assertEqual(load_saved_games(self.db, self.project), [self.game, self.other])

    def test_cleanup_failure_does_not_report_successful_save_as_failure(self):
        with patch("pathlib.Path.unlink", side_effect=PermissionError("locked")):
            path = replace_cover(self.db, self.project, self.game, self.new_image.read_bytes())
        self.assertTrue(path.is_file())
        self.assertTrue(self.game["cover_path"].is_file())
        self.assertEqual(load_saved_games(self.db, self.project)[0]["cover_path"], path)

    def test_delete_removes_only_requested_record_and_owned_copy(self):
        delete_game(self.db, self.project, self.game["id"])
        self.assertEqual(load_saved_games(self.db, self.project), [self.other])
        self.assertFalse(self.game["cover_path"].exists())
        self.assertTrue(self.other["cover_path"].exists())
        self.assertTrue(self.original.exists())
        with self.assertRaises(ValueError):
            delete_game(self.db, self.project, self.game["id"])

    def test_delete_database_failure_keeps_record_and_file(self):
        with patch("retro_beaten.services.collection.delete_saved_game", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaises(sqlite3.Error):
                delete_game(self.db, self.project, self.game["id"])
        self.assertEqual(load_saved_games(self.db, self.project), [self.game, self.other])
        self.assertTrue(self.game["cover_path"].exists())

    def test_external_or_shared_cover_is_preserved(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE games SET cover_path=? WHERE id=?",
                               (str(self.original), self.game["id"]))
            connection.commit()
        delete_game(self.db, self.project, self.game["id"])
        self.assertTrue(self.original.exists())
        shared = register_manual_game(self.db, self.project, "Shared", "PC", "playing", self.original)
        alias = "assets/images/../images/" + self.other["cover_path"].name
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE games SET cover_path=? WHERE id=?", (alias, shared["id"]))
            connection.commit()
        delete_game(self.db, self.project, self.other["id"])
        self.assertTrue(self.other["cover_path"].exists())


class EditCollectionUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close_root)
        self.original = self.project / "original.png"
        Image.new("RGB", (30, 40), "navy").save(self.original)
        self.game = dict(id=1, name="My game", platform="PS1", status="beaten",
                         cover_path=self.original, summary="", igdb_id=None)

    def close_root(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def test_preview_cancel_and_save_exact_preview_bytes(self):
        calls = []
        window = CoverWindow(self.root, self.game, lambda *args: calls.append(args))
        window.withdraw()
        window.load_preview(self.original)
        self.assertEqual(calls, [])
        with patch("retro_beaten.ui.cover_window.filedialog.askopenfilename", return_value=""):
            window.choose_image()
        self.assertEqual(window.image_data, self.original.read_bytes())
        window.cancel_button.invoke()
        self.assertEqual(calls, [])
        window = CoverWindow(self.root, self.game, lambda *args: calls.append(args))
        window.withdraw()
        window.load_preview(self.original)
        data = self.original.read_bytes()
        Image.new("RGB", (40, 30), "green").save(self.original)
        window.save_button.invoke()
        self.assertEqual(calls, [(self.game, data)])

    def test_invalid_preview_and_save_failure_allow_retry(self):
        window = CoverWindow(self.root, self.game, lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
        window.withdraw()
        window.load_preview(self.original)
        invalid = self.project / "invalid.png"
        invalid.write_bytes(b"invalid")
        window.load_preview(invalid)
        self.assertIsNone(window.image_data)
        self.assertEqual(window.save_button.cget("state"), "disabled")
        window.load_preview(self.original)
        window.save_cover()
        self.assertTrue(window.winfo_exists())
        self.assertEqual(window.save_button.cget("state"), "normal")
        self.assertIn("kept", window.message.cget("text"))

    def test_delete_requires_confirmation_and_reports_failure(self):
        calls = []
        details = DetailsWindow(self.root, self.game, "#E7B84B", on_delete=calls.append)
        details.withdraw()
        with patch("retro_beaten.ui.details_window.messagebox.askyesno", return_value=False) as confirm:
            details.delete_button.invoke()
        self.assertEqual(calls, [])
        self.assertIn("My game (PlayStation 1)", confirm.call_args.args[1])
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        details.on_delete = lambda game: (_ for _ in ()).throw(sqlite3.OperationalError("locked"))
        with patch("retro_beaten.ui.details_window.messagebox.askyesno", return_value=True), \
             patch("retro_beaten.ui.details_window.messagebox.showerror") as error:
            details.delete_button.invoke()
        error.assert_called_once()
        self.assertTrue(details.winfo_exists())
        details.on_delete = calls.append
        with patch("retro_beaten.ui.details_window.messagebox.askyesno", return_value=True):
            details.delete_button.invoke()
        self.assertEqual(calls, [self.game])
        self.assertFalse(details.winfo_exists())

    def test_main_updates_details_library_and_database_then_deletes(self):
        db = self.project / "data/retro_beaten.db"
        initialize_database(db)
        record = register_manual_game(db, self.project, "My game", "PS1", "beaten", self.original)
        other = register_manual_game(db, self.project, "Other game", "PC", "wishlist", self.original)
        errors = []

        def report(kind, error, traceback):
            errors.append(error)
            self.root.quit()

        self.root.report_callback_exception = report

        def exercise():
            game = next(g for g in rendering.call_args.args[1] if g["id"] == record["id"])
            rendering.call_args.args[3](game)
            details = next(w for w in self.root.winfo_children() if isinstance(w, DetailsWindow))
            details.change_cover_button.invoke()
            self.root.after(100, lambda: save(details, game))

        def save(details, game):
            details.cover_window.load_preview(self.original)
            details.cover_window.save_button.invoke()
            self.root.after(100, lambda: remove(details, game))

        def remove(details, game):
            saved = next(g for g in load_saved_games(db, self.project) if g["id"] == game["id"])
            self.assertEqual(game["cover_path"], saved["cover_path"])
            self.assertNotEqual(saved["cover_path"], record["cover_path"])
            self.assertIsNotNone(details.cover_display)
            with patch("retro_beaten.ui.details_window.messagebox.askyesno", return_value=True):
                details.delete_button.invoke()
            self.root.after(100, finish)

        def finish():
            self.assertEqual(load_saved_games(db, self.project), [other])
            self.assertEqual(rendering.call_args.args[1], [other])
            self.assertTrue(self.original.exists())
            self.root.quit()

        with patch("retro_beaten.app.create_window", return_value=self.root), \
             patch("retro_beaten.app.render_library", wraps=render_library) as rendering, \
             patch("sys.stdout", new_callable=StringIO):
            self.root.after(200, exercise)
            self.root.after(5000, lambda: report(None, AssertionError("Test did not finish"), None))
            application.RetroBeatenApp(self.project).run()
        self.assertEqual(errors, [])
