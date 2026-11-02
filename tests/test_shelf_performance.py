"""Regression checks for shelf reuse and deferred cover decoding."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import customtkinter as ctk
from PIL import Image
from retro_beaten.ui.library_view import create_library_area, render_library
from retro_beaten.ui.cover_cache import load_thumbnail, _thumbnail


class ShelfReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close)
        self.area = create_library_area(self.root)
        self.cover = Path(self.temp.name) / "cover.png"
        Image.new("RGB", (600, 800), "navy").save(self.cover)
        self.games = [dict(id=i, name=str(i), platform=platform, status="beaten", cover_path=self.cover)
                      for i, platform in enumerate(("PC", "PS1"))]
        self.preferences = dict(cover_size="Medium", sort_order="Name A-Z", sections={})

    def close(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()
        _thumbnail.cache_clear()

    def render(self):
        render_library(self.area, self.games, lambda *args: None, lambda *args: None,
                       preferences=self.preferences,
                       on_section_toggle=lambda key, value: self.preferences["sections"].update({key: value}))

    def test_unchanged_shelf_reused_and_only_changed_card_rebuilt(self):
        self.render()
        pc = self.area._shelf_cache["beaten:PC"][1]
        ps1 = self.area._shelf_cache["beaten:PS1"][1]
        with patch("retro_beaten.ui.library_view.create_cover") as create:
            self.render()
            create.assert_not_called()
        self.assertIs(self.area._shelf_cache["beaten:PC"][1], pc)
        previous_card = ps1._cards[1][1]
        self.games[1]["name"] = "Edited"
        self.render()
        self.assertIs(self.area._shelf_cache["beaten:PC"][1], pc)
        self.assertIs(self.area._shelf_cache["beaten:PS1"][1], ps1)
        self.assertIsNot(ps1._cards[1][1], previous_card)
        self.games.pop()
        self.render()
        self.assertNotIn("beaten:PS1", self.area._shelf_cache)

    def test_missing_and_corrupt_covers_remain_accessible_and_recover(self):
        self.cover.unlink()
        self.render()
        section = self.area._shelf_cache["beaten:PC"][1]
        missing = section._cards[0][1]
        self.assertTrue(missing.winfo_exists())
        self.cover.write_bytes(b"invalid image")
        self.render()
        damaged = section._cards[0][1]
        self.assertIsNot(missing, damaged)
        Image.new("RGB", (300, 400), "green").save(self.cover)
        self.render()
        self.assertIsNot(damaged, section._cards[0][1])

    def test_new_platforms_render_as_separate_shelves(self):
        self.games = [dict(id=i, name=code, platform=code, status="beaten",
                           cover_path=self.cover)
                      for i, code in enumerate(("PS3", "3DS", "SWITCH"))]
        self.render()
        self.assertEqual(set(self.area._shelf_cache),
                         {"beaten:PS3", "beaten:3DS", "beaten:SWITCH"})

    def test_collapsed_section_loads_only_once_on_expansion(self):
        self.preferences["sections"]["beaten:PS1"] = False
        self.render()
        section = self.area._shelf_cache["beaten:PS1"][1]
        panel = next(child for child in section.winfo_children() if isinstance(child, ctk.CTkFrame))
        self.assertEqual(panel.winfo_children(), [])
        button = next(child for child in section.winfo_children() if isinstance(child, ctk.CTkButton))
        button.invoke()
        cover = panel.winfo_children()[0]
        button.invoke()
        button.invoke()
        self.assertIs(panel.winfo_children()[0], cover)
        self.assertTrue(self.preferences["sections"]["beaten:PS1"])

    def test_cache_invalidates_changed_file_and_bounds_thumbnail(self):
        first, size = load_thumbnail(self.cover, (150, 200))
        self.assertEqual(size, (150, 200))
        self.assertLessEqual(first.width, 300)
        self.assertIs(load_thumbnail(self.cover, (150, 200))[0], first)
        Image.new("RGB", (900, 1000), "red").save(self.cover)
        second, _ = load_thumbnail(self.cover, (150, 200))
        self.assertIsNot(first, second)
        self.assertEqual(second.getpixel((0, 0)), (255, 0, 0))

    def test_sorting_and_favoriting_do_not_recreate_large_pc_shelf(self):
        from retro_beaten.ui.library_view import update_favorite_display
        self.games = [dict(self.games[0], id=i, name=f"Game {i:03}") for i in range(150)]
        self.render()
        section = self.area._shelf_cache["beaten:PC"][1]
        cards = {key: value[1] for key, value in section._cards.items()}
        with patch("retro_beaten.ui.library_view.create_cover") as create:
            self.games[100]["favorite"] = True
            update_favorite_display(self.area, self.games[100])
            self.preferences["sort_order"] = "Name Z-A"
            self.render()
            create.assert_not_called()
        self.assertEqual(cards, {key: value[1] for key, value in section._cards.items()})
        self.assertEqual(cards[100].favorite_star.cget("text_color"), "#E7B84B")
        self.games.pop()
        self.render()
        self.assertEqual(len(section._cards), 149)
        self.assertIs(section._cards[100][1], cards[100])

    def test_size_change_keeps_card_controls_and_updates_image_dimensions(self):
        self.render()
        section = self.area._shelf_cache["beaten:PC"][1]
        card = section._cards[0][1]
        star = card.favorite_star
        self.preferences["cover_size"] = "Small"
        self.render()
        self.assertIs(section._cards[0][1], card)
        self.assertIs(card.favorite_star, star)
        self.assertEqual(card.winfo_children()[0].cget("image").cget("size"), (105, 140))

    def test_incremental_loading_yields_and_cancels_obsolete_work(self):
        import time
        self.root.geometry("1000x700")
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.root.update()
        self.games = [dict(self.games[0], id=i, name=f"Game {i:03}") for i in range(100)]
        render_library(self.area, self.games, lambda *args: None, lambda *args: None, incremental=True)
        section = self.area._shelf_cache["beaten:PC"][1]
        self.assertTrue(section._rendering)
        self.assertLess(len(section._cards), 100)
        # A new search replaces the unfinished build instead of appending old cards.
        render_library(self.area, self.games[:2], lambda *args: None, lambda *args: None, incremental=True)
        deadline = time.monotonic()+3
        while time.monotonic() < deadline and (section._rendering or set(section._cards) != {0, 1}):
            self.root.update()
        self.root.update()
        self.assertFalse(section._rendering)
        self.assertEqual(set(section._cards), {0, 1})
        render_library(self.area, self.games, lambda *args: None, lambda *args: None, incremental=True)
        section.destroy()
        self.root.update()
