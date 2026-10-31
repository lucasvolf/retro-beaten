"""Silent entry point and stable paths after package separation."""

from contextlib import redirect_stdout
import importlib
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

import main
from retro_beaten.app import RetroBeatenApp
from retro_beaten.paths import PROJECT_DIR
from retro_beaten.services.collection import register_manual_game
from retro_beaten.services.igdb_api import load_credentials
from retro_beaten.storage.database import initialize_database, load_saved_games


class EntryPointTests(unittest.TestCase):
    def test_import_is_silent_and_does_not_open_window_database_or_network(self):
        output = StringIO()
        with redirect_stdout(output), \
             patch("retro_beaten.app.create_window") as window, \
             patch("retro_beaten.app.initialize_database") as database, \
             patch("urllib.request.urlopen") as network:
            importlib.reload(main)
        self.assertEqual(output.getvalue(), "")
        window.assert_not_called()
        database.assert_not_called()
        network.assert_not_called()

    def test_entry_point_starts_the_application(self):
        with patch("main.RetroBeatenApp") as application, redirect_stdout(StringIO()) as output:
            main.main()
        application.assert_called_once_with()
        application.return_value.run.assert_called_once_with()
        self.assertEqual(output.getvalue(), "")

    def test_env_is_still_loaded_from_project_root(self):
        with tempfile.TemporaryDirectory() as folder:
            old_cwd = Path.cwd()
            try:
                os.chdir(folder)
                with patch("retro_beaten.services.igdb_api.load_dotenv") as dotenv, \
                     patch.dict(os.environ, {"IGDB_CLIENT_ID": "test-id", "IGDB_CLIENT_SECRET": "test-secret"}):
                    self.assertEqual(load_credentials(), ("test-id", "test-secret"))
                self.assertEqual(dotenv.call_args.args[0], PROJECT_DIR / ".env")
                self.assertEqual(PROJECT_DIR, Path(__file__).resolve().parents[1])
            finally:
                os.chdir(old_cwd)

    def test_startup_loads_existing_collection_without_listing_games(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                db = project / "data/retro_beaten.db"
                initialize_database(db)
                cover = project / "source.png"
                Image.new("RGB", (30, 40), "navy").save(cover)
                game = register_manual_game(db, project, "My game", "PS1", "beaten", cover)
                before = load_saved_games(db, project)
                with patch("retro_beaten.app.create_window", return_value=root), \
                     redirect_stdout(StringIO()) as output:
                    app = RetroBeatenApp(project)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(app.games, [game])
                self.assertEqual(load_saved_games(db, project), before)
                self.assertTrue(app.library_area.winfo_exists())
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()
