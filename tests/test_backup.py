"""Backup and restore tests use temporary collections only."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import customtkinter as ctk
from PIL import Image

from retro_beaten.app import RetroBeatenApp
from retro_beaten.services.backup import create_backup, restore_backup
from retro_beaten.services.collection import register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.ui.backup_window import BackupWindow


class BackupFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.target = self.base / "destination"
        self.db = self.source / "data/retro_beaten.db"
        self.target_db = self.target / "data/retro_beaten.db"
        initialize_database(self.db)
        initialize_database(self.target_db)
        self.image = self.base / "original cover.png"
        Image.new("RGB", (60, 80), "navy").save(self.image)
        self.game = register_manual_game(self.db, self.source, "Café's Adventure", "PS1", "beaten",
                                         self.image, "First line\nSecond line")
        self.previous = register_manual_game(self.target_db, self.target, "Previous collection", "PC",
                                             "wishlist", self.image, "Keep")
        self.archive = self.base / "collection.zip"

    def records(self, database=None, project=None):
        return load_saved_games(database or self.target_db, project or self.target)

    def rewrite_archive(self, change):
        with ZipFile(self.archive) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        manifest = json.loads(entries["collection.json"])
        change(manifest, entries)
        entries["collection.json"] = json.dumps(manifest).encode("utf-8")
        with ZipFile(self.archive, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)


class BackupServiceTests(BackupFixture):
    def test_portable_round_trip_preserves_records_covers_and_safety_backup(self):
        for index, status in enumerate(("playing", "dropped", "wishlist")):
            register_manual_game(self.db, self.source, f"Game {index}", "PSP", status, self.image)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE games SET igdb_id=306134 WHERE id=?", (self.game["id"],))
            connection.commit()
        (self.source / ".env").write_text("FAKE_TEST_SECRET=do-not-export")
        (self.source / "data/recommendations.json").write_text("[]")
        self.assertEqual(create_backup(self.db, self.source, self.archive), 4)
        with ZipFile(self.archive) as archive:
            self.assertEqual(len(archive.namelist()), 5)
            self.assertTrue(all(n == "collection.json" or n.startswith("covers/") for n in archive.namelist()))
        result = restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(result["count"], 4)
        expected = self.records(self.db, self.source)
        actual = self.records()
        for old, new in zip(expected, actual):
            self.assertEqual({k: v for k, v in old.items() if k != "cover_path"},
                             {k: v for k, v in new.items() if k != "cover_path"})
            self.assertEqual(old["cover_path"].read_bytes(), new["cover_path"].read_bytes())
            self.assertTrue(new["cover_path"].is_relative_to(self.target / "assets/images"))
        self.assertTrue(self.previous["cover_path"].is_file())
        self.assertTrue(self.image.is_file())
        restore_backup(self.target_db, self.target, result["safety_backup"])
        restored = self.records()[0]
        self.assertEqual(restored["name"], self.previous["name"])
        self.assertEqual(restored["summary"], self.previous["summary"])

    def test_empty_collection_can_be_exported_and_restored(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("DELETE FROM games")
            connection.commit()
        self.assertEqual(create_backup(self.db, self.source, self.archive), 0)
        result = restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(self.records(), [])
        self.assertTrue(result["safety_backup"].exists())

    def test_export_failure_preserves_existing_backup_and_removes_temporary_file(self):
        create_backup(self.db, self.source, self.archive)
        before = self.archive.read_bytes()
        files = set(self.base.iterdir())
        self.game["cover_path"].unlink()
        with self.assertRaisesRegex(ValueError, "Cover not found"):
            create_backup(self.db, self.source, self.archive)
        self.assertEqual(self.archive.read_bytes(), before)
        self.assertEqual(set(self.base.iterdir()), files)

    def test_invalid_archives_do_not_change_collection_or_create_safety_backup(self):
        def future_version(manifest, entries):
            manifest["version"] = 999

        def traversal(manifest, entries):
            manifest["games"][0]["cover_path"] = "../outside.png"

        def extra_file(manifest, entries):
            entries["../../escape.txt"] = b"never extract"

        def missing_cover(manifest, entries):
            del entries[manifest["games"][0]["cover_path"]]

        def corrupted_cover(manifest, entries):
            entries[manifest["games"][0]["cover_path"]] = b"changed"

        def invalid_image(manifest, entries):
            data = b"not an image"
            entries[manifest["games"][0]["cover_path"]] = data
            manifest["games"][0]["sha256"] = sha256(data).hexdigest()

        def unknown_status(manifest, entries):
            manifest["games"][0]["status"] = "unknown"

        def duplicate_id(manifest, entries):
            manifest["games"].append(manifest["games"][0].copy())

        before = self.records()
        files = set((self.target / "assets/images").iterdir())
        for change in (future_version, traversal, extra_file, missing_cover, corrupted_cover,
                       invalid_image, unknown_status, duplicate_id):
            with self.subTest(case=change.__name__):
                create_backup(self.db, self.source, self.archive)
                self.rewrite_archive(change)
                with self.assertRaises(ValueError):
                    restore_backup(self.target_db, self.target, self.archive)
                self.assertEqual(self.records(), before)
                self.assertEqual(set((self.target / "assets/images").iterdir()), files)
                self.assertFalse((self.target / "backups").exists())
        self.archive.write_bytes(b"not a zip")
        with self.assertRaises(ValueError):
            restore_backup(self.target_db, self.target, self.archive)

    def test_archive_limits_and_duplicate_entries_are_rejected(self):
        create_backup(self.db, self.source, self.archive)
        with patch("retro_beaten.services.backup.MAX_TOTAL_BYTES", 1):
            with self.assertRaises(ValueError):
                restore_backup(self.target_db, self.target, self.archive)
        with ZipFile(self.archive, "a") as archive:
            with self.assertWarns(UserWarning):
                archive.writestr("collection.json", "{}")
        with self.assertRaises(ValueError):
            restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(self.records(), [self.previous])

    def test_failed_safety_backup_prevents_restore(self):
        create_backup(self.db, self.source, self.archive)
        files = set((self.target / "assets/images").iterdir())
        with patch("retro_beaten.services.backup.create_backup", side_effect=PermissionError("blocked")):
            with self.assertRaises(PermissionError):
                restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(self.records(), [self.previous])
        self.assertEqual(set((self.target / "assets/images").iterdir()), files)

    def test_insert_failure_rolls_back_deletion_and_removes_only_new_covers(self):
        create_backup(self.db, self.source, self.archive)
        with closing(sqlite3.connect(self.target_db)) as connection:
            connection.execute("CREATE TRIGGER reject_restore BEFORE INSERT ON games BEGIN SELECT RAISE(ABORT, 'teste'); END")
            connection.commit()
        files = set((self.target / "assets/images").iterdir())
        with self.assertRaises(sqlite3.Error):
            restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(self.records(), [self.previous])
        self.assertEqual(set((self.target / "assets/images").iterdir()), files)
        self.assertEqual(len(list((self.target / "backups").glob("*.zip"))), 1)

    def test_failed_cover_write_keeps_old_collection(self):
        create_backup(self.db, self.source, self.archive)
        original_open = Path.open

        def fail_write(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError("blocked")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", fail_write):
            with self.assertRaises(PermissionError):
                restore_backup(self.target_db, self.target, self.archive)
        self.assertEqual(self.records(), [self.previous])


class BackupUITests(BackupFixture):
    def setUp(self):
        super().setUp()
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close_root)

    def close_root(self):
        for child in self.root.winfo_children():
            child.destroy()
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)

    def test_cancelled_dialogs_and_confirmation_do_not_start_operations(self):
        window = BackupWindow(self.root, self.target_db, self.target, lambda: None)
        with patch.object(window, "start") as start, \
             patch("retro_beaten.ui.backup_window.filedialog.asksaveasfilename", return_value=""), \
             patch("retro_beaten.ui.backup_window.filedialog.askopenfilename", return_value=""):
            window.export()
            window.restore()
            start.assert_not_called()
        with patch.object(window, "start") as start, \
             patch("retro_beaten.ui.backup_window.filedialog.askopenfilename", return_value=str(self.archive)), \
             patch("retro_beaten.ui.backup_window.messagebox.askyesno", return_value=False) as confirm:
            window.restore()
            self.assertEqual(confirm.call_args.kwargs["default"], "no")
            self.assertIn(str(self.archive), confirm.call_args.args[1])
            start.assert_not_called()
        self.assertEqual(self.records(), [self.previous])

    def test_error_reenables_controls_and_does_not_reload_collection(self):
        calls = []
        window = BackupWindow(self.root, self.target_db, self.target, lambda: calls.append(True))
        window.busy = True
        window.close()
        self.assertTrue(window.winfo_exists())
        window.results.put(("error", "Invalid file", self.archive))
        window.poll()
        self.assertFalse(window.busy)
        self.assertEqual(window.restore_button.cget("state"), "normal")
        self.assertIn("Invalid file", window.message.cget("text"))
        self.assertEqual(calls, [])

    def test_application_export_then_restore_refreshes_shelf_and_closes_old_details(self):
        create_backup(self.db, self.source, self.archive)
        errors, completed = [], []
        exported = self.base / "ui-backup.zip"

        def report(kind, error, traceback):
            errors.append(error)
            self.root.quit()

        self.root.report_callback_exception = report

        def export():
            app.open_details(app.games[0])
            app.open_backup()
            self.assertIs(app.backup_window.grab_current(), app.backup_window)
            with patch("retro_beaten.ui.backup_window.filedialog.asksaveasfilename", return_value=str(exported)):
                app.backup_window.export_button.invoke()
            self.assertTrue(app.backup_window.busy)
            self.root.after(100, wait_export)

        def wait_export():
            if app.backup_window.busy:
                self.root.after(100, wait_export)
                return
            self.assertTrue(exported.is_file())
            with patch("retro_beaten.ui.backup_window.filedialog.askopenfilename", return_value=str(self.archive)), \
                 patch("retro_beaten.ui.backup_window.messagebox.askyesno", return_value=True):
                app.backup_window.restore_button.invoke()
            self.root.after(100, wait_restore)

        def wait_restore():
            if app.backup_window.busy:
                self.root.after(100, wait_restore)
                return
            self.assertIn("Collection restored: 1", app.backup_window.message.cget("text"))
            self.assertEqual(app.games[0]["name"], self.game["name"])
            self.assertEqual(app.games, self.records())
            self.assertIsNone(app.details_window)
            self.assertTrue(app.library_area.winfo_children())
            completed.append(True)
            self.root.quit()

        with patch("retro_beaten.app.create_window", return_value=self.root):
            app = RetroBeatenApp(self.target)
            self.root.after(200, export)
            self.root.after(8000, lambda: report(None, AssertionError("Test did not finish"), None))
            app.run()
        self.assertEqual(errors, [])
        self.assertEqual(completed, [True])
