"""Shelf tool behavior with synthetic images and isolated collection data."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import customtkinter as ctk
from PIL import Image
from retro_beaten.services.shelf_tools import export_shelf, save_background, pick_wishlist, section_order
from retro_beaten.storage.preferences import save_preferences, load_preferences
from retro_beaten.app import RetroBeatenApp


class ShelfToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.cover = self.folder / "my cover.png"
        Image.new("RGB", (300, 400), "navy").save(self.cover)
        self.games = [dict(id=i, name=f"Game {i}", status=status, platform="PS1", cover_path=self.cover)
                      for i, status in enumerate(("beaten", "wishlist", "wishlist"))]

    def test_random_pick_only_wishlist_and_no_immediate_repeat(self):
        self.assertIsNone(pick_wishlist([]))
        game = pick_wishlist(self.games, previous=1)
        self.assertEqual(game["id"], 2)
        self.assertEqual(game["status"], "wishlist")
        self.assertEqual(pick_wishlist(self.games[:2], previous=1)["id"], 1)

    def test_export_scope_and_failed_write_preserve_existing_image(self):
        path = self.folder / "shelf.png"
        export_shelf(self.games, path, {}, "Beaten only")
        with Image.open(path) as image:
            self.assertEqual(image.width, 1600)
            height = image.height
        export_shelf(self.games, path, {}, "Entire collection")
        with Image.open(path) as image:
            self.assertGreater(image.height, height)
        original = path.read_bytes()
        with patch("PIL.Image.Image.save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                export_shelf(self.games, path, {})
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError):
            export_shelf([], path, {})

    def test_background_copy_and_preferences_roundtrip(self):
        stored = save_background(self.cover, self.folder)
        self.cover.unlink()
        self.assertTrue(stored.exists())
        prefs = {"cover_size": "Medium", "sort_order": "Name A-Z", "sections": {},
                 "section_order": section_order(["beaten:PS1"]),
                 "background_enabled": True, "background_darkness": 70}
        path = self.folder / "data/preferences.json"
        save_preferences(path, prefs)
        self.assertEqual(load_preferences(path), {**prefs, "sidebar_expanded": True})
        with self.assertRaises(OSError):
            save_background(self.cover, self.folder)
        self.assertTrue(stored.exists())

    def test_tools_native_drop_order_and_background(self):
        root = ctk.CTk()
        root.geometry("1000x800")
        root.attributes("-alpha", 0)
        try:
            with patch("retro_beaten.app.create_window", return_value=root):
                app = RetroBeatenApp(self.folder)
            app.games = self.games
            app.refresh_library()
            self.assertIsNotNone(app.drop_handler)
            self.assertTrue(root.tk.call("bind", root._w, "<<Drop>>"))
            app.drop_handler(SimpleNamespace(data=root.tk.call("list", str(self.cover))))
            self.assertEqual(app.manual_window.cover_path, self.cover)
            app.manual_window.destroy()
            app.open_shelf_tools()
            tools = app.tools_window
            tools.listbox.selection_clear(0, "end")
            tools.listbox.selection_set(1)
            tools.move(-1)
            self.assertEqual(app.preferences["section_order"][0], "wishlist")
            first = app.library_area.pack_slaves()[0]
            self.assertIs(first, app.library_area._shelf_cache["wishlist"][1])
            save_background(self.cover, self.folder)
            app.preferences["background_enabled"] = True
            app.update_background()
            root.update()
            app.background.draw()
            self.assertIsNotNone(app.background.photo)
            tools.remove_background()
            self.assertEqual(app.background.label.winfo_manager(), "")
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()
