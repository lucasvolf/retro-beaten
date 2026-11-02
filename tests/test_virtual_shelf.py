"""Viewport regression tests use synthetic records and no personal data."""
import tempfile
import time
import unittest
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from retro_beaten.ui.library_view import create_library_area, render_library, update_favorite_display


class VirtualShelfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.geometry("1100x760")
        self.root.attributes("-alpha", 0)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args[1]))
        self.addCleanup(self.close)
        self.area = create_library_area(self.root)
        self.cover = Path(self.temp.name) / "cover.png"
        Image.new("RGB", (300, 400), "navy").save(self.cover)
        self.games = [dict(id=i, name=f"Game {i:04}", platform="PC", status="beaten",
                           cover_path=self.cover, favorite=False) for i in range(500)]
        self.preferences = dict(cover_size="Medium", sort_order="Name A-Z", sections={})
        self.opened = []
        self.root.update()

    def close(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def settle(self):
        deadline = time.monotonic() + 10
        stable = None
        def check():
            nonlocal stable
            busy = any(s._rendering for _, s in getattr(self.area, "_shelf_cache", {}).values())
            if busy:
                stable = None
            elif stable is None:
                stable = time.monotonic()
            if time.monotonic() > deadline or (stable and time.monotonic()-stable > .2):
                self.root.quit()
            else:
                self.root.after(20, check)
        self.root.after(20, check)
        self.root.mainloop()
        self.assertLess(time.monotonic(), deadline, "Viewport did not settle")
        self.assertEqual(self.errors, [])

    def render(self, query="", exhibition=False):
        def favorite(game, value):
            game["favorite"] = value
            update_favorite_display(self.area, game)
        render_library(self.area, self.games, lambda *args: None,
                       lambda game: self.opened.append(game["id"]), query=query,
                       preferences=self.preferences, exhibition=exhibition,
                       on_favorite_change=favorite, incremental=True)
        self.settle()
        return self.area._shelf_cache["beaten:PC"][1]

    def test_scroll_releases_offscreen_cards_and_preserves_actions(self):
        section = self.render()
        self.assertIn(0, section._cards)
        self.assertLess(len(section._cards), 60)
        self.assertNotIn(499, section._cards)
        self.games[499]["favorite"] = True
        update_favorite_display(self.area, self.games[499])
        self.area._parent_canvas.yview_moveto(1)
        self.settle()
        self.assertIn(499, section._cards)
        self.assertNotIn(0, section._cards)
        self.assertLess(len(section._cards), 60)
        frame = section._cards[499][1]
        self.assertEqual(frame.favorite_star.cget("text_color"), "#E7B84B")
        frame.favorite_star.invoke()
        self.assertFalse(self.games[499]["favorite"])
        surface = section._virtual_shelf.surface
        x, y, width, height = frame.bounds
        surface.event_generate("<Motion>", x=round(x+width/2), y=round(y+height/2))
        surface.event_generate("<Button-1>", x=round(x+width/2), y=round(y+height/2))
        self.assertEqual(self.opened, [499])
        margin = round(frame.scale*3)
        self.assertEqual(frame.surface.coords(frame.image_item)[1]-frame.bounds[1], margin)
        self.area._parent_canvas.yview_moveto(0)
        self.settle()
        self.assertIn(0, section._cards)
        self.assertNotIn(499, section._cards)

    def test_resize_sort_search_and_exhibition_reconcile_all_visible_cards(self):
        section = self.render()
        self.preferences["cover_size"] = "Small"
        section = self.render()
        for _, frame in section._cards.values():
            self.assertEqual(frame.display_size, (105, 140))
        self.preferences["sort_order"] = "Name Z-A"
        self.render()
        self.assertIn(499, section._cards)
        self.assertNotIn(0, section._cards)
        self.render(exhibition=True)
        self.assertTrue(all(frame.favorite_star.cget("state") == "disabled"
                            for _, frame in section._cards.values()))
        section = self.render(query="Game 0001")
        self.assertEqual(set(section._cards), {1})
        self.assertEqual(section._cards[1][1].favorite_star.cget("state"), "normal")

    def test_collapse_and_multiple_shelves_load_only_visible_section(self):
        self.games += [dict(self.games[0], id=1000+i, platform="PS3", name=f"PS3 {i}") for i in range(200)]
        pc = self.render()
        ps3 = self.area._shelf_cache["beaten:PS3"][1]
        self.assertFalse(ps3._cards)
        pc._set_expanded(False)
        self.settle()
        self.assertFalse(pc._cards)
        self.assertTrue(ps3._cards)
        self.assertLess(len(ps3._cards), 60)
        pc._set_expanded(True)
        self.settle()
        self.assertTrue(pc._cards)
        self.assertFalse(ps3._cards)

    def test_last_partial_row_stays_centered_after_window_resize(self):
        self.games += [dict(self.games[0], id=500+i, name=f"Game {500+i:04}") for i in range(3)]
        section = self.render()
        self.root.geometry("980x650")
        self.settle()
        self.area._parent_canvas.yview_moveto(1)
        self.settle()
        self.assertIn(502, section._cards)
        frames = [frame for _, frame in section._cards.values()]
        last_y = max(frame.bounds[1] for frame in frames)
        row = [frame for frame in frames if frame.bounds[1] == last_y]
        left = min(frame.bounds[0] for frame in row)
        right = max(frame.bounds[0]+frame.width for frame in row)
        self.assertAlmostEqual((left + right) / 2, section.winfo_x()+section._covers_panel.winfo_x()+section._covers_panel.winfo_width()/2, delta=2)
        for frame in frames:
            margin = round(frame.scale*3)
            x, y = frame.surface.coords(frame.image_item)
            self.assertEqual(y-frame.bounds[1], margin)
            self.assertEqual(x-frame.bounds[0], margin)

    def test_thousand_medium_covers_reach_bottom_with_native_geometry_intact(self):
        self.games += [dict(self.games[0], id=i, name=f"Game {i:04}") for i in range(500, 1000)]
        section = self.render()
        self.area._parent_canvas.yview_moveto(1)
        self.settle()
        self.assertIn(999, section._cards)
        self.assertLess(len(section._cards), 60)
        frame = section._cards[999][1]
        self.assertGreaterEqual(frame.winfo_rooty(), self.area._parent_canvas.winfo_rooty())
        self.assertLess(frame.winfo_rooty(), self.root.winfo_rooty() + self.root.winfo_height())
        margin = round(frame.scale*3)
        self.assertEqual(frame.surface.coords(frame.image_item)[1]-frame.bounds[1], margin)

    def test_initially_collapsed_shelf_keeps_header_and_expands(self):
        self.preferences["sections"]["beaten:PC"] = False
        section = self.render()
        self.assertFalse(section._cards)
        self.assertTrue(section._virtual_shelf.header_visible)
        section._title_button.invoke()
        self.settle()
        self.assertTrue(section._cards)

    def test_header_after_tall_shelf_remains_in_viewport(self):
        self.games += [dict(self.games[0], id=i, name=f"Game {i:04}") for i in range(500, 1000)]
        self.games += [dict(self.games[0], id=2000+i, name=f"PS3 {i}", platform="PS3") for i in range(10)]
        self.render()
        self.area._parent_canvas.yview_moveto(1)
        self.settle()
        section = self.area._shelf_cache["beaten:PS3"][1]
        self.assertEqual(len(section._cards), 10)
        shelf = section._virtual_shelf
        self.assertTrue(shelf.header_visible)
        self.assertGreaterEqual(shelf.header_bounds[1], 0)
        self.assertLess(shelf.header_bounds[1], shelf.surface.winfo_height())

    def test_invalidated_recommendations_show_message_without_stale_cards(self):
        from retro_beaten.ui.library_view import clear_recommended_display
        recommendations = [dict(self.games[0], id=f"recommended:{i}", status="recommended") for i in range(20)]
        render_library(self.area, [], lambda *args: None, lambda *args: None,
                       recommendations=recommendations, incremental=True)
        self.settle()
        section = self.area._shelf_cache["recommended"][1]
        clear_recommended_display(self.area)
        self.settle()
        self.assertFalse(section._cards)
        self.assertEqual(section._virtual_shelf.surface.itemcget(section._virtual_shelf.message_label, "state"), "normal")
        render_library(self.area, [], lambda *args: None, lambda *args: None,
                       recommendations=[], incremental=True)
        self.settle()
        self.assertTrue(section._virtual_shelf.closed)

    def test_canvas_star_click_and_mouse_wheel_route_to_correct_actions(self):
        section = self.render()
        card = section._cards[0][1]
        surface = section._virtual_shelf.surface
        x, y, width, height = card.bounds
        point = (round(x+width-18*card.scale), round(y+height-18*card.scale))
        surface.event_generate("<Motion>", x=point[0], y=point[1])
        surface.event_generate("<Button-1>", x=point[0], y=point[1])
        self.assertTrue(self.games[0]["favorite"])
        self.assertEqual(self.opened, [])
        before = self.area._parent_canvas.yview()[0]
        surface.event_generate("<MouseWheel>", delta=-120, x=200, y=300)
        self.settle()
        self.assertGreater(self.area._parent_canvas.yview()[0], before)
        self.assertTrue(section._cards)

    def test_empty_search_message_is_painted_above_scroll_frame(self):
        self.render()
        render_library(self.area, self.games, lambda *args: None, lambda *args: None,
                       query="nothing-matches", incremental=True)
        self.settle()
        viewport = self.area._shelf_viewport
        self.assertIn("No games found", viewport.surface.itemcget(viewport.empty_item, "text"))
        self.assertFalse(viewport.shelves)
        self.render()
        self.assertIsNone(viewport.empty_item)

    def test_destroy_pending_shelf_unregisters_viewport(self):
        section = self.render()
        section._update_records(self.games, (210, 280), False)
        viewport = self.area._shelf_viewport
        shelf = section._virtual_shelf
        section.destroy()
        self.settle()
        self.assertNotIn(shelf, viewport.shelves)

    def test_refresh_detects_visible_cover_replacement_without_checking_every_record(self):
        from unittest.mock import patch
        with patch("retro_beaten.ui.library_view.cover_signature") as full_shelf_stat:
            section = self.render()
            full_shelf_stat.assert_not_called()
        previous = section._cards[0][1]
        Image.new("RGB", (250, 500), "green").save(self.cover)
        self.render()
        self.assertIsNot(section._cards[0][1], previous)
        self.assertEqual(section._cards[0][1].display_size, (100, 200))
