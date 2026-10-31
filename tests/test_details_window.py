"""Offline details, cover clicks, and PC platform selection."""

import re
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten.ui.details_window import DetailsWindow
from retro_beaten.ui.cover_card import create_cover, attach_details_click, attach_status_menu
from retro_beaten.ui.search_window import SearchWindow


class DetailsWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close_root)
        self.project = Path(self.temp.name)
        cover = self.project / "preview.jpg"
        Image.new("RGB", (300, 400), "navy").save(cover)
        self.game = {
            "id": 1, "name": "PC game", "platform": "PC", "status": "beaten",
            "summary": "A saved description in the database.", "igdb_id": 999,
            "cover_path": cover
        }

    def close_root(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def test_details_use_local_data_and_update_status(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("No network requests in details")):
            window = DetailsWindow(self.root, self.game, "#E7B84B")
            window.withdraw()
            self.assertEqual(window.name_label.cget("text"), self.game["name"])
            self.assertEqual(window.platform_label.cget("text"), "Platform: PC")
            self.assertEqual(window.description_box.get("1.0", "end").strip(), self.game["summary"])
            self.assertEqual(window.description_box.cget("state"), "disabled")
            self.assertIsNotNone(window.cover_display)
            self.assertEqual(window.cover_display.cget("size"), (240, 320))
            window.update_status("playing", "#3B82F6")
            self.assertEqual(window.status_label.cget("text"), "Playing")
            self.assertEqual(window.status_label.cget("text_color"), "#3B82F6")
            window.destroy()

    def test_missing_cover_and_summary_have_fallbacks(self):
        self.game["cover_path"] = self.project / "assets/previews/missing_test_image.jpg"
        self.game["summary"] = None
        window = DetailsWindow(self.root, self.game, "#E7B84B")
        window.withdraw()
        self.assertIsNone(window.cover_display)
        self.assertEqual(window.cover_label.cget("text"), "Cover unavailable")
        self.assertIn("saved description", window.description_box.get("1.0", "end"))
        window.destroy()

    def test_cover_and_border_click_keep_correct_game_and_right_menu(self):
        selected = []
        for game_id in (1, 2):
            game = dict(self.game, id=game_id)
            frame, label = create_cover(self.root, game["cover_path"], (150, 200), "beaten")
            attach_status_menu(frame, label, game, lambda *args: None)
            attach_details_click(frame, label, game, selected.append)
            # Invoke Tk callbacks without opening visible windows.
            for widget in (frame._canvas, label._label):
                binding = widget.bind("<Button-1>")
                callback_id = re.search(r"\[([^\s]+)", binding).group(1)
                widget.tk.call(callback_id, "test_event")
                self.assertTrue(widget.bind("<Button-3>"))
            frame.destroy()
        self.assertEqual([game["id"] for game in selected], [1, 1, 2, 2])

    def test_pc_selection_sends_windows_platform_to_search(self):
        received = []

        def search(name, platform_id, queue):
            received.append((name, platform_id))
            queue.put(("success", []))

        with patch("retro_beaten.ui.search_window.run_search", side_effect=search):
            window = SearchWindow(self.root, lambda *args: None, self.project)
            window.withdraw()
            window.console_menu.set("PC")
            window.name_entry.insert(0, "Portal")
            window.start_search()
            deadline = time.monotonic() + 3
            while window.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.02)
            self.assertFalse(window.busy)
            self.assertEqual(received, [("Portal", 6)])
            self.assertEqual(window.selected_platform_code, "PC")
            window.destroy()


if __name__ == "__main__":
    unittest.main()
