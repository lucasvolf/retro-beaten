"""Window integration with local registration and no network requests."""

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

import retro_beaten.ui.search_window as search_window
from retro_beaten.services.collection import register_game
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.ui.library_view import create_library_area, render_library


class SearchWindowTests(unittest.TestCase):
    def test_selection_registration_duplicate_and_close(self):
        game = {
            "id": 306134, "name": "Tekken 3", "summary": "Test description",
            "platforms": [{"id": 7, "name": "PlayStation"}],
            "cover": {"image_id": "co8d7r"}
        }
        root = ctk.CTk()
        root.withdraw()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            with tempfile.TemporaryDirectory() as folder:
                project = Path(folder)
                preview = project / "preview.jpg"
                Image.new("RGB", (300, 400), "navy").save(preview)
                db = project / "data/test.db"
                initialize_database(db)
                library = create_library_area(root)

                def add_game(selected, platform, status, path):
                    register_game(db, project, selected, platform, status, path)
                    for section in library.winfo_children():
                        section.destroy()
                    render_library(library, load_saved_games(db, project), lambda *args: None, lambda game: None)

                def fake_search(name, platform_id, queue):
                    self.assertEqual(platform_id, 7)
                    queue.put(("success", [game]))

                def fake_preview(selected, destination_dir, queue):
                    queue.put(("preview", preview))

                def finish(window):
                    deadline = time.monotonic() + 3
                    while window.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.02)
                    self.assertFalse(window.busy)
                    self.assertEqual(errors, [])

                with patch.object(search_window, "run_search", side_effect=fake_search), patch.object(search_window, "run_preview", side_effect=fake_preview):
                    window = search_window.SearchWindow(root, add_game, project)
                    window.withdraw()
                    window.name_entry.insert(0, "Tekken 3")
                    window.start_search()
                    finish(window)
                    self.assertEqual(window.add_button.cget("state"), "disabled")
                    choice = next(iter(window.result_choices))
                    window.select_result(choice)
                    finish(window)
                    self.assertEqual(window.add_button.cget("state"), "normal")
                    window.game_status_menu.set("Playing")
                    window.add_selected_game()
                    self.assertTrue(window.already_added)
                    self.assertEqual(len(library.winfo_children()), 1)
                    saved = load_saved_games(db, project)
                    self.assertEqual(len(saved), 1)
                    self.assertEqual(saved[0]["status"], "playing")
                    self.assertEqual(saved[0]["summary"], game["summary"])

                    window.select_result(choice)
                    finish(window)
                    window.add_selected_game()
                    self.assertIn("already in your collection", window.status_label.cget("text"))
                    self.assertEqual(len(load_saved_games(db, project)), 1)
                    window.clear_results()
                    self.assertIsNone(window.selected_game)
                    self.assertIsNone(window.preview_path)
                    self.assertEqual(window.add_button.cget("state"), "disabled")

                    no_cover = dict(game, id=123, cover=None)
                    window.games = [no_cover]
                    window.result_choices = {"No cover": no_cover}
                    window.select_result("No cover")
                    self.assertFalse(window.busy)
                    self.assertEqual(window.add_button.cget("state"), "disabled")
                    window.destroy()

                    window = search_window.SearchWindow(root, add_game, project)
                    window.withdraw()
                    window.games = [game]
                    window.selected_platform_code = "PS1"
                    window.result_choices = {"Tekken 3": game}
                    window.select_result("Tekken 3")
                    self.assertIsNotNone(window.poll_id)
                    window.destroy()
                    root.update()
                    self.assertEqual(errors, [])
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
