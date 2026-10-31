"""Editing with temporary databases, failures, and interface updates."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten.app import RetroBeatenApp
from retro_beaten.library import filter_games
from retro_beaten.services.collection import edit_game_details, register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.ui.edit_game_window import EditGameWindow


class DetailsEditFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data/retro_beaten.db"
        initialize_database(self.db)
        self.source = self.project / "source.png"
        Image.new("RGB", (30, 40), "navy").save(self.source)
        self.game = register_manual_game(self.db, self.project, "Original", "PS1", "playing",
                                         self.source, "Original description")
        self.other = register_manual_game(self.db, self.project, "Other", "PC", "beaten", self.source)


class DetailsEditTests(DetailsEditFixture):
    def test_save_preserves_identity_cover_status_platform_and_other_records(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE games SET igdb_id=123 WHERE id=?", (self.game["id"],))
            conn.commit()
        self.game["igdb_id"] = 123
        cover_bytes = self.game["cover_path"].read_bytes()
        fields = edit_game_details(self.db, self.game["id"], "  Café's Adventure  ", "  Line 1\nLine 2  ")
        records = {g["id"]: g for g in load_saved_games(self.db, self.project)}
        self.assertEqual(fields, dict(name="Café's Adventure", summary="Line 1\nLine 2"))
        self.assertEqual(records[self.game["id"]], {**self.game, **fields})
        self.assertEqual(records[self.other["id"]], self.other)
        self.assertEqual(cover_bytes, self.game["cover_path"].read_bytes())
        edit_game_details(self.db, self.game["id"], "Other", "")  # The same name on another platform is allowed.
        saved = next(g for g in load_saved_games(self.db, self.project) if g["id"] == self.game["id"])
        self.assertEqual(saved["summary"], "")

    def test_invalid_name_duplicate_and_missing_record_leave_database_unchanged(self):
        register_manual_game(self.db, self.project, "Café", "PS1", "beaten", self.source)
        before = load_saved_games(self.db, self.project)
        for name in ("   ", "---", "ca-fe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                edit_game_details(self.db, self.game["id"], name, "Do not save")
        with self.assertRaises(ValueError):
            edit_game_details(self.db, 9999, "Missing", "")
        self.assertEqual(load_saved_games(self.db, self.project), before)

    def test_existing_same_title_can_still_edit_description(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("UPDATE games SET platform='PS1', name='Original' WHERE id=?", (self.other["id"],))
            conn.commit()
        edit_game_details(self.db, self.game["id"], "Original", "New description")
        saved = next(g for g in load_saved_games(self.db, self.project) if g["id"] == self.game["id"])
        self.assertEqual(saved["summary"], "New description")

    def test_sql_failure_rolls_back_both_fields(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TRIGGER reject_edit BEFORE UPDATE ON games BEGIN SELECT RAISE(ABORT, 'teste'); END")
            conn.commit()
        before = load_saved_games(self.db, self.project)
        with self.assertRaises(sqlite3.Error):
            edit_game_details(self.db, self.game["id"], "New", "New")
        self.assertEqual(load_saved_games(self.db, self.project), before)


class DetailsEditUITests(DetailsEditFixture):
    # Persistence tests in the class above do not create windows.
    def setUp(self):
        super().setUp()
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close_root)

    def close_root(self):
        # Destroying child windows may schedule scaling adjustments in remaining windows.
        for child in self.root.winfo_children():
            child.destroy()
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()
        # The Tcl interpreter remains alive; CTk destruction may create timers.
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)

    def test_prefilled_form_cancel_does_not_save(self):
        with patch("retro_beaten.ui.edit_game_window.EditGameWindow.save") as save:
            window = EditGameWindow(self.root, self.game, save)
            self.assertEqual(window.name_entry.get(), self.game["name"])
            self.assertEqual(window.summary_box.get("1.0", "end-1c"), self.game["summary"])
            window.name_entry.insert(0, "Changed ")

            def cancel():
                window.cancel_button.invoke()
                self.root.quit()

            # Allow Windows to process window creation before clicking.
            self.root.after(300, cancel)
            self.root.mainloop()
            save.assert_not_called()
        self.assertEqual(load_saved_games(self.db, self.project), [self.game, self.other])

    def test_application_save_error_retry_and_details_refresh(self):
        errors = []
        completed = []

        def report(kind, error, traceback):
            errors.append(error)
            self.root.quit()

        self.root.report_callback_exception = report

        def open_form():
            app.open_details(app.games[0])
            app.details_window.edit_button.invoke()
            form = app.details_window.edit_window
            app.details_window.open_edit_window()
            self.assertIs(form, app.details_window.edit_window)
            self.root.after(100, exercise)

        def exercise():
            details = app.details_window
            form = details.edit_window
            form.name_entry.delete(0, "end")
            form.save_button.invoke()
            self.assertIn("Enter", form.message.cget("text"))
            form.name_entry.insert(0, "Zelda")
            form.summary_box.delete("1.0", "end")
            form.summary_box.insert("1.0", "My adventure\nFinished!")
            with patch("retro_beaten.app.edit_game_details", side_effect=sqlite3.OperationalError("locked")):
                form.save_button.invoke()
            self.assertTrue(form.winfo_exists())
            self.assertEqual(form.save_button.cget("state"), "normal")
            self.assertEqual(details.game["name"], "Original")
            self.assertEqual(details.name_label.cget("text"), "Original")
            self.assertEqual(form.name_entry.get(), "Zelda")
            self.assertEqual(load_saved_games(self.db, self.project), [self.game, self.other])
            form.save_button.invoke()
            self.assertFalse(form.winfo_exists())
            self.root.after(100, verify)

        def verify():
            details = app.details_window
            self.assertEqual(details.name_label.cget("text"), "Zelda")
            self.assertIn("Zelda", details.title())
            self.assertEqual(details.description_box.get("1.0", "end-1c"), "My adventure\nFinished!")
            self.assertEqual(details.description_box.cget("state"), "disabled")
            self.assertEqual([g["name"] for g in app.games], ["Other", "Zelda"])
            self.assertEqual(filter_games(app.games, "zelda"), [details.game])
            self.assertEqual(filter_games(app.games, "original"), [])
            self.assertEqual(load_saved_games(self.db, self.project), app.games)
            completed.append(True)
            self.root.quit()

        with patch("retro_beaten.app.create_window", return_value=self.root):
            app = RetroBeatenApp(self.project)
            self.root.after(200, open_form)
            self.root.after(5000, lambda: report(None, AssertionError("Test did not finish"), None))
            app.run()
        self.assertEqual(errors, [])
        self.assertEqual(completed, [True])
