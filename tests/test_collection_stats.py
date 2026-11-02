"""Accurate collection counts and an empty-safe, live dashboard."""

import unittest
import customtkinter as ctk
from retro_beaten.services.collection_stats import collection_stats
from retro_beaten.ui.overview_window import OverviewWindow


class CollectionStatsTests(unittest.TestCase):
    def test_statuses_platforms_and_recommendations(self):
        games = [dict(status="beaten", platform="PS1", favorite=True),
                 dict(status="beaten", platform="PC"), dict(status="dropped", platform="PS1"),
                 dict(status="playing", platform="GBA"), dict(status="wishlist", platform="PSP"),
                 dict(status="recommended", platform="PC")]
        stats = collection_stats(games)
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["favorites"], 1)
        self.assertEqual(stats["statuses"], dict(beaten=2, playing=1, wishlist=1, dropped=1))
        self.assertEqual(stats["platforms"]["PS1"], dict(beaten=1, dropped=1))
        self.assertEqual(collection_stats([])["total"], 0)

    def test_dashboard_empty_filters_and_refresh(self):
        root = ctk.CTk()
        root.withdraw()
        games = []
        try:
            window = OverviewWindow(root, lambda: games)
            window.withdraw()
            self.assertEqual(window.count_labels["beaten"].cget("text"), "0")
            games.extend([dict(status="beaten", platform="PS1"), dict(status="dropped", platform="PC")])
            window.refresh()
            self.assertEqual(window.count_labels["beaten"].cget("text"), "1")
            for status in ("Dropped", "Playing", "All statuses"):
                window.status_menu.set(status)
                window.draw_chart()
                self.assertTrue(window.chart.find_all())
            games[0]["status"] = "dropped"
            window.refresh()
            self.assertEqual(window.count_labels["dropped"].cget("text"), "2")
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()
