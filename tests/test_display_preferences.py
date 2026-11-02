"""Display settings persist without modifying collection data."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten.app import RetroBeatenApp
from retro_beaten.library import sort_games
from retro_beaten.storage.preferences import load_preferences, save_preferences, COVER_SIZES
from retro_beaten.services.collection import register_manual_game


class PreferenceTests(unittest.TestCase):
    def test_roundtrip_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data/preferences.json"
            preferences = load_preferences(path)
            preferences.update(cover_size="Large", sort_order="Recently added",
                               sections={"beaten:PS1": False})
            save_preferences(path, preferences)
            self.assertEqual(load_preferences(path), preferences)
            path.write_text('{"cover_size": [], "sections": {"PC": 1}}')
            self.assertEqual(load_preferences(path)["cover_size"], "Medium")
            self.assertEqual(load_preferences(path)["sections"], {})
            path.write_text("broken")
            self.assertEqual(load_preferences(path)["sort_order"], "Name A-Z")

    def test_sort_keeps_records_intact(self):
        games = [{"id": 4, "name": "Zelda"}, {"id": 8, "name": "Abzu"}]
        self.assertEqual(sort_games(games, "Name A-Z"), games[::-1])
        self.assertEqual(sort_games(games, "Name Z-A"), games)
        self.assertEqual(sort_games(games, "Recently added"), games[::-1])
        self.assertEqual(games[0]["name"], "Zelda")


class DisplayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.geometry("1000x800")
        self.root.attributes("-alpha", 0)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.addCleanup(self.close)
        with patch("retro_beaten.app.create_window", return_value=self.root):
            self.app = RetroBeatenApp(self.temp.name)
        cover = Path(self.temp.name) / "source.png"
        Image.new("RGB", (300, 400), "navy").save(cover)
        game = register_manual_game(self.app.database_path, self.app.project_dir,
                                    "Test game", "PS1", "beaten", cover)
        self.app.show_added_game(game)

    def close(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def panel(self):
        # Reused widgets keep creation order even when their visual order changes.
        section = self.app.library_area._shelf_cache["beaten:PS1"][1]
        return section._covers_panel

    def settle(self):
        self.root.update()
        self.app.library_area._parent_canvas.yview_moveto(1)
        self.root.after(250, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.errors, [])

    def test_size_collapse_reload_and_exhibition(self):
        app = self.app
        before = app.database_path.read_bytes()
        for size, dimensions in COVER_SIZES.items():
            app.change_view("cover_size", size)
            self.settle()
            card = next(iter(self.panel().master._cards.values()))[1]
            self.assertEqual(card.display_size, dimensions)
        section = self.panel().master
        toggle = section._title_button
        toggle.invoke()
        app.refresh_library()
        self.assertEqual(self.panel().winfo_manager(), "")
        saved = load_preferences(app.preferences_path)
        self.assertFalse(saved["sections"]["beaten:PS1"])
        app.preferences = saved
        app.refresh_library()
        self.assertEqual(self.panel().winfo_manager(), "")
        app.remember_section("beaten:PS1", True)
        for _ in range(2):
            app.toggle_exhibition()
            self.settle()
            self.assertFalse(app.header.winfo_ismapped())
            self.assertTrue(app.exhibition_bar.winfo_ismapped())
            card = next(iter(self.panel().master._cards.values()))[1]
            self.assertTrue(card.exhibition)
            self.assertFalse(card.surface.tag_bind(card.tag, "<Button-1>"))
            app.exit_exhibition()
            self.settle()
            self.assertTrue(app.header.winfo_ismapped())
            self.assertTrue(app.view_controls.winfo_ismapped())
            self.assertFalse(app.exhibition_bar.winfo_ismapped())
        self.assertEqual(before, app.database_path.read_bytes())
