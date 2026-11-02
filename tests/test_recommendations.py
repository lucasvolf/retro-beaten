"""Varied recommendations, offline cache, and safe Wishlist migration."""

from collections import Counter
from contextlib import closing
from pathlib import Path
import random
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image

from retro_beaten.services.collection import register_game, register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games, update_game_status
from retro_beaten.ui.details_window import DetailsWindow
from retro_beaten.ui.library_view import render_library
from retro_beaten.ui.manual_game_window import ManualGameWindow
from retro_beaten.platforms import PLATFORMS
from retro_beaten.ui.recommendation_controls import RecommendationControls
from retro_beaten.services.recommendations import (
    build_profile, exclude_collection, fetch_recommendations, select_recommendations,
    load_recommendations, save_recommendations,
)
from retro_beaten.ui.search_window import SearchWindow
from retro_beaten.statuses import STATUS_BORDER_COLORS
from retro_beaten import app as application


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.db = self.project / "data/test.db"
        initialize_database(self.db)
        self.source = self.project / "cover.jpg"
        Image.new("RGB", (30, 40), "navy").save(self.source)

    def candidate(self, game_id, platform="PS1", name=None):
        return {"id": game_id, "name": name or f"Game {game_id}", "genres": [{"id": 1, "name": "Role-playing"}],
                "themes": [{"id": 2, "name": "Science fiction"}],
                "platforms": [{"id": PLATFORMS[platform]["igdb_id"]}],
                "cover": {"image_id": f"cover{game_id}"}, "summary": "Description"}

    def profile(self, name="My Beaten"):
        seed = self.candidate(9999, name=name)
        return build_profile([seed], [dict(igdb_id=9999, favorite=True, status="beaten", platform="PC")])

    def pools(self):
        return {code: [self.candidate(index * 100 + i, code) for i in range(1, 11)]
                for index, code in enumerate(PLATFORMS, 1)}

    def test_round_robin_variety_and_refresh_avoid_previous_batch(self):
        profile = self.profile()
        first = select_recommendations(self.pools(), [], profile, rng=random.Random(1))
        second = select_recommendations(self.pools(), [], profile,
                                        [g["igdb_id"] for g in first], rng=random.Random(1))
        self.assertEqual(len(first), 20)
        self.assertEqual(set(g["platform"] for g in first), set(PLATFORMS))
        counts = Counter(g["platform"] for g in first).values()
        self.assertLessEqual(max(counts) - min(counts), 1)
        self.assertTrue({g["igdb_id"] for g in first}.isdisjoint(g["igdb_id"] for g in second))
        self.assertTrue(all("My Beaten" in game["reason"] for game in first))

    def test_excludes_all_collection_statuses_manual_names_and_duplicate_ports(self):
        collection = [dict(id=i, igdb_id=i, name=f"Game {i}", status=status)
                      for i, status in enumerate(("beaten", "playing", "dropped", "wishlist"), 1)]
        collection.append(dict(id=99, igdb_id=None, name="TO THE MÓON", status="wishlist"))
        candidates = [self.candidate(i) for i in range(1, 6)]
        candidates.append(self.candidate(6, name="To the Moon"))
        self.assertEqual([g["id"] for g in exclude_collection(candidates, collection)], [5])
        shared = self.candidate(7)
        shared["platforms"].append({"id": 8})
        selected = select_recommendations(
            {"PS1": [shared], "PS2": [shared, self.candidate(8, "PS2")]}, [],
            self.profile(), rng=random.Random(1),
        )
        self.assertEqual(len(selected), 2)
        self.assertEqual({g["platform"] for g in selected}, {"PS1", "PS2"})
        self.assertEqual(len({g["igdb_id"] for g in selected}), 2)

    def test_profile_keeps_individual_favorites_from_each_platform(self):
        seeds = [{"id": i, "name": str(i), "genres": [1 if i < 101 else 2]} for i in range(1, 102)]
        collection = [dict(igdb_id=i, status="beaten", favorite=True, platform="PC" if i < 101 else "GBA")
                      for i in range(1, 102)]
        collection.append(dict(igdb_id=200, status="playing", platform="PS1"))
        seeds.append({"id": 200, "name": "Not beaten", "genres": [3], "similar_games": [999]})
        profile = build_profile(seeds, collection)
        self.assertEqual(len(profile), 101)
        self.assertEqual({seed.id for seed in profile}, set(range(1, 102)))
        self.assertFalse(any(999 in seed.related for seed in profile))

    def test_offline_cache_and_wishlist_keep_independent_cover(self):
        folder = self.project / "assets/recommendations"
        folder.mkdir(parents=True)
        cover = folder / "igdb_7.jpg"
        cover.write_bytes(self.source.read_bytes())
        game = self.candidate(7)
        suggestion = {**game, "id": "recommended:7:PS1", "igdb_id": 7,
                      "platform": "PS1", "status": "recommended", "cover_path": cover}
        save_recommendations(self.project, [suggestion])
        self.assertEqual(load_recommendations(self.project, []), [suggestion])
        record = register_game(self.db, self.project, game, "PS1", "wishlist", cover)
        self.assertEqual(load_saved_games(self.db, self.project), [record])
        self.assertEqual(load_recommendations(self.project, [record]), [])
        save_recommendations(self.project, [])
        cover.unlink()
        self.assertTrue(record["cover_path"].is_file())
        self.assertEqual(record["cover_path"].read_bytes(), self.source.read_bytes())
        for status in ("playing", "beaten", "dropped", "wishlist"):
            update_game_status(self.db, record["id"], status)
            self.assertEqual(load_saved_games(self.db, self.project)[0]["status"], status)

    def test_cache_failure_keeps_old_list(self):
        cover = self.project / "assets/recommendations/igdb_7.jpg"
        cover.parent.mkdir(parents=True)
        cover.write_bytes(self.source.read_bytes())
        suggestion = {**self.candidate(7), "igdb_id": 7, "platform": "PS1",
                      "status": "recommended", "cover_path": cover}
        save_recommendations(self.project, [suggestion])
        with patch("pathlib.Path.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                save_recommendations(self.project, [])
        self.assertEqual(load_recommendations(self.project, []), [suggestion])

    def test_legacy_cached_reason_uses_english_without_changing_game_data(self):
        cover = self.project / "assets/recommendations/igdb_7.jpg"
        cover.parent.mkdir(parents=True)
        cover.write_bytes(self.source.read_bytes())
        suggestion = {**self.candidate(7), "igdb_id": 7, "platform": "PS1",
                      "status": "recommended", "cover_path": cover,
                      "reason": "Legacy cached explanation"}
        save_recommendations(self.project, [suggestion])
        cached = (self.project / "data/recommendations.json").read_bytes()
        loaded = load_recommendations(self.project, [])
        self.assertEqual(loaded, [{**suggestion, "reason": "Based on your favorite Beaten collection."}])
        self.assertEqual((self.project / "data/recommendations.json").read_bytes(), cached)

    def test_existing_checked_database_migrates_without_losing_records_or_constraints(self):
        old_db = self.project / "old.db"
        with closing(sqlite3.connect(old_db)) as connection:
            connection.execute("""CREATE TABLE games (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, platform TEXT NOT NULL,
                cover_path TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL CHECK(status IN ('beaten','playing','dropped')),
                igdb_id INTEGER, summary TEXT NOT NULL DEFAULT '')""")
            connection.execute("CREATE UNIQUE INDEX games_igdb_platform ON games(igdb_id,platform)")
            connection.execute("INSERT INTO games VALUES (42,'My game','PS1','assets/old.jpg','beaten',7,'Description')")
            connection.commit()
        before = load_saved_games(old_db, self.project)
        initialize_database(old_db)
        initialize_database(old_db)
        self.assertEqual(load_saved_games(old_db, self.project), before)
        self.assertEqual(load_saved_games(self.project / "old.before_wishlist.db", self.project), before)
        update_game_status(old_db, 42, "wishlist")
        self.assertEqual(load_saved_games(old_db, self.project)[0]["status"], "wishlist")
        with closing(sqlite3.connect(old_db)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE games SET status='recommended'")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO games (id,name,platform,cover_path,status,igdb_id,summary) VALUES (43,'Duplicado','PS1','other.jpg','beaten',7,'')")

    def test_fetch_queries_every_platform_with_richer_metadata(self):
        collection = [dict(id=1, igdb_id=1, name="Beaten", status="beaten", favorite=True, platform="PC")]
        pools = self.pools()
        responses = [[self.candidate(1, name="Beaten")], *pools.values()]
        with patch("retro_beaten.services.recommendations.load_credentials", return_value=("id", "secret")), \
             patch("retro_beaten.services.recommendations.get_access_token", return_value="token"), \
             patch("retro_beaten.services.recommendations.query_games", side_effect=responses) as query, \
             patch("retro_beaten.services.recommendations.download_cover", return_value=self.source):
            result = fetch_recommendations(collection, [], self.project)
        self.assertEqual(len(result), 20)
        self.assertEqual({g["platform"] for g in result}, set(PLATFORMS))
        self.assertEqual(query.call_count, 1 + len(PLATFORMS))
        with patch("retro_beaten.services.recommendations.load_credentials") as credentials:
            with self.assertRaisesRegex(ValueError, "Beaten"):
                fetch_recommendations([], [], self.project)
            credentials.assert_not_called()


class RecommendationUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.withdraw()
        self.addCleanup(self.close_root)
        self.project = Path(self.temp.name)
        self.cover = self.project / "preview.jpg"
        Image.new("RGB", (300, 400), "navy").save(self.cover)
        self.game = dict(id="recommended:1:PS1", igdb_id=1, name="Recommendation", platform="PS1",
                         status="recommended", cover_path=self.cover, reason="Related to a Beaten game.")

    def close_root(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def test_recommended_details_action_colors_and_local_search(self):
        selected = []
        window = DetailsWindow(self.root, self.game, STATUS_BORDER_COLORS["recommended"], selected.append)
        window.withdraw()
        window.wishlist_button.invoke()
        self.assertEqual(selected, [self.game])
        panel = ctk.CTkFrame(self.root)
        render_library(panel, [], lambda *args: None, selected.append, "Recommendation", [self.game])
        self.assertEqual(len(panel.winfo_children()), 1)
        section = panel.winfo_children()[0]
        cover_panel = next(w for w in section.winfo_children() if isinstance(w, ctk.CTkFrame))
        frame = cover_panel.winfo_children()[0]
        self.assertEqual(frame.cget("border_color"), "#9CA3AF")
        wishlist = {**self.game, "id": 1, "status": "wishlist"}
        render_library(panel, [wishlist], lambda *args: None, selected.append)
        section = panel.winfo_children()[-1]
        cover_panel = next(w for w in section.winfo_children() if isinstance(w, ctk.CTkFrame))
        self.assertEqual(cover_panel.winfo_children()[0].cget("border_color"), "#22C55E")

    def test_manual_and_igdb_forms_translate_wishlist_label(self):
        saved = []
        manual = ManualGameWindow(self.root, lambda *args: saved.append(args))
        manual.withdraw()
        manual.name_entry.insert(0, "Want to play")
        manual.status_menu.set("Wishlist")
        manual.load_cover(self.cover)
        manual.save_game()
        self.assertEqual(saved[-1][2], "wishlist")
        search = SearchWindow(self.root, lambda *args: saved.append(args), self.project)
        search.withdraw()
        search.selected_game = self.game
        search.selected_platform_code = "PS1"
        search.preview_path = self.cover
        search.game_status_menu.set("Wishlist")
        search.add_selected_game()
        self.assertEqual(saved[-1][2], "wishlist")

    def test_background_error_preserves_previous_recommendations_and_allows_retry(self):
        old = [self.game]
        accepted = []
        controls = RecommendationControls(self.root, self.project, lambda: [], lambda: old,
                                            lambda games: accepted.append(games))
        with patch("retro_beaten.ui.recommendation_controls.fetch_recommendations", side_effect=TimeoutError):
            controls.start_refresh()
            deadline = time.monotonic() + 3
            while controls.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
        self.assertFalse(controls.busy)
        self.assertEqual(controls.button.cget("state"), "normal")
        self.assertEqual(accepted, [])
        self.assertEqual(old, [self.game])
        self.assertIn("Previous", controls.message.cget("text"))
        controls.destroy()

    def test_main_refresh_open_details_and_save_to_wishlist(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            cache = project / "assets/recommendations"
            cache.mkdir(parents=True)
            cover = cache / "igdb_1.jpg"
            cover.write_bytes(self.cover.read_bytes())
            suggestion = {**self.game, "cover_path": cover, "platforms": [{"id": 7}]}
            second = {**suggestion, "id": "recommended:2:PS2", "igdb_id": 2,
                      "name": "Another recommendation", "platform": "PS2", "platforms": [{"id": 8}]}
            errors = []

            def report(error_type, error, traceback):
                errors.append(error)
                self.root.quit()

            self.root.report_callback_exception = report

            def start():
                controls = app.recommendation_controls
                controls.button.invoke()
                self.root.after(150, lambda: finish(controls))

            def finish(controls):
                if controls.busy:
                    self.root.after(50, lambda: finish(controls))
                    return
                self.assertEqual(load_recommendations(project, []), [suggestion, second])
                # Callback used by covers on the main shelf.
                rendering.call_args.args[3](suggestion)
                details = next(w for w in self.root.winfo_children() if isinstance(w, DetailsWindow))
                details.wishlist_button.invoke()
                games = load_saved_games(project / "data/retro_beaten.db", project)
                self.assertEqual(len(games), 1)
                self.assertEqual(games[0]["status"], "wishlist")
                self.assertNotEqual(games[0]["cover_path"], cover)
                self.assertEqual(load_recommendations(project, games), [second])
                self.assertEqual(rendering.call_args.args[5], [second])
                self.root.quit()

            def timeout():
                errors.append(AssertionError("Refresh did not finish"))
                self.root.quit()

            with patch("retro_beaten.app.create_window", return_value=self.root), \
                 patch("retro_beaten.app.render_library", wraps=render_library) as rendering, \
                 patch("retro_beaten.ui.recommendation_controls.fetch_recommendations", return_value=[suggestion, second]):
                app = application.RetroBeatenApp(project)
                self.root.after(0, start)
                self.root.after(5000, timeout)
                app.run()
            self.assertEqual(errors, [])
