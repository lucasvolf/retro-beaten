"""Favorites persistence, legacy restore, and recommendation eligibility."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
import customtkinter as ctk
from PIL import Image
from retro_beaten.app import RetroBeatenApp
from retro_beaten.services.collection import register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games, update_game_favorite
from retro_beaten.services.backup import create_backup, restore_backup
from retro_beaten.services.recommendations import build_profile, fetch_recommendations, recommendation_seeds, save_recommendations, load_recommendations


class FavoriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data/test.db"
        initialize_database(self.db)
        self.cover = self.project / "cover.png"
        Image.new("RGB", (150, 200), "navy").save(self.cover)
        self.game = register_manual_game(self.db, self.project, "Adventure", "PS1", "beaten", self.cover)

    def test_persistence_backup_and_legacy_restore(self):
        update_game_favorite(self.db, self.game["id"], True)
        initialize_database(self.db)
        self.assertTrue(load_saved_games(self.db, self.project)[0]["favorite"])
        archive = self.project / "favorites.zip"
        create_backup(self.db, self.project, archive)
        update_game_favorite(self.db, self.game["id"], False)
        restore_backup(self.db, self.project, archive)
        self.assertTrue(load_saved_games(self.db, self.project)[0]["favorite"])
        with ZipFile(archive) as zipped:
            entries = {name: zipped.read(name) for name in zipped.namelist()}
        manifest = json.loads(entries["collection.json"])
        manifest["version"] = 1
        for game in manifest["games"]:
            del game["favorite"]
        entries["collection.json"] = json.dumps(manifest).encode()
        legacy = self.project / "legacy.zip"
        with ZipFile(legacy, "w") as zipped:
            for name, data in entries.items():
                zipped.writestr(name, data)
        restore_backup(self.db, self.project, legacy)
        self.assertFalse(load_saved_games(self.db, self.project)[0]["favorite"])

    def test_only_favorite_beaten_igdb_games_seed_recommendations(self):
        collection = [dict(self.game, id=i, igdb_id=i, favorite=favorite, status=status)
                      for i, favorite, status in ((1, True, "beaten"), (2, False, "beaten"), (3, True, "playing"))]
        seeds = [dict(id=i, name=str(i), genres=[i]) for i in (1, 2, 3)]
        self.assertEqual({seed.id for seed in build_profile(seeds, collection)}, {1})
        self.assertEqual(recommendation_seeds(collection), ["PS1:1"])
        with patch("retro_beaten.services.recommendations.load_credentials") as credentials:
            with self.assertRaisesRegex(ValueError, "Star at least one"):
                fetch_recommendations([self.game], [], self.project)
            credentials.assert_not_called()

    def test_star_click_persists_without_opening_details(self):
        root = ctk.CTk()
        root.geometry("1100x900")
        root.attributes("-alpha", 0)
        try:
            with patch("retro_beaten.app.create_window", return_value=root):
                app = RetroBeatenApp(self.project)
            game = register_manual_game(app.database_path, self.project, "Star test", "PS1", "beaten", self.cover)
            app.show_added_game(game)
            section = app.library_area._shelf_cache["beaten:PS1"][1]
            panel = next(child for child in section.winfo_children() if isinstance(child, ctk.CTkFrame))
            deadline = time.monotonic() + 5
            def wait_for_card():
                app.library_area._parent_canvas.yview_moveto(1)
                if game["id"] in section._cards or time.monotonic() > deadline:
                    root.quit()
                else:
                    root.after(20, wait_for_card)
            root.after(20, wait_for_card)
            root.mainloop()
            self.assertIn(game["id"], section._cards)
            card = section._cards[game["id"]][1]
            self.assertEqual(card.favorite_star.cget("text_color"), "#64748B")
            with patch.object(app, "refresh_library") as refresh:
                card.favorite_star.invoke()
                root.update_idletasks()
                refresh.assert_not_called()
            self.assertEqual(card.favorite_star.cget("text_color"), "#E7B84B")
            self.assertTrue(load_saved_games(app.database_path, self.project)[0]["favorite"])
            self.assertIsNone(app.details_window)
            card.favorite_star.invoke()
            self.assertFalse(load_saved_games(app.database_path, self.project)[0]["favorite"])
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()

    def test_cache_rejects_old_or_changed_favorite_profile(self):
        folder = self.project / "assets/recommendations"
        folder.mkdir(parents=True)
        cover = folder / "cover.png"
        cover.write_bytes(self.cover.read_bytes())
        suggestion = dict(self.game, id="recommended:99:PS1", igdb_id=99,
                          status="recommended", name="Suggestion", cover_path=cover)
        seeds = [dict(self.game, igdb_id=7, favorite=True)]
        save_recommendations(self.project, [suggestion], seeds)
        self.assertEqual(load_recommendations(self.project, seeds), [suggestion])
        self.assertEqual(load_recommendations(self.project, [dict(seeds[0], favorite=False)]), [])
        (self.project / "data/recommendations.json").write_text("[]")
        self.assertEqual(load_recommendations(self.project, seeds), [])

    def test_in_flight_results_rejected_after_favorite_change(self):
        from retro_beaten.ui.recommendation_controls import RecommendationControls
        from unittest.mock import Mock
        root = ctk.CTk()
        root.withdraw()
        try:
            collection = [dict(self.game, igdb_id=7, favorite=True)]
            accept = Mock()
            controls = RecommendationControls(root, self.project, lambda: collection, lambda: [], accept)
            controls.request_seeds = recommendation_seeds(collection)
            controls.busy = True
            collection[0]["favorite"] = False
            controls.queue.put(("success", []))
            controls.check_results()
            accept.assert_not_called()
            self.assertIn("changed", controls.message.cget("text"))
            self.assertFalse(controls.busy)
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()
