"""Affinity regressions using synthetic metadata, without network calls."""
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retro_beaten.platforms import PLATFORMS
from retro_beaten.services.recommendation_matching import best_match, build_profile, candidate_filters
from retro_beaten.services.recommendations import select_recommendations, fetch_recommendations, save_recommendations, load_recommendations


def game(identity, name="Game", platform="PC", **overrides):
    return dict(id=identity, name=name, platforms=[{"id": PLATFORMS[platform]["igdb_id"]}],
                cover={"image_id": "test"}, **{
                    "genres": [{"id": 12, "name": "Role-playing"}],
                    "themes": [{"id": 18, "name": "Science fiction"}],
                    "player_perspectives": [{"id": 1, "name": "First person"}],
                    **overrides})


def collection(*seeds):
    return [dict(igdb_id=seed["id"], name=seed["name"], favorite=True,
                 status="beaten", platform="PC") for seed in seeds]


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.seed = game(1, "Future RPG")
        self.profile = build_profile([self.seed], collection(self.seed))

    def test_generic_genre_perspective_and_related_link_are_insufficient(self):
        self.seed["similar_games"] = [2]
        self.profile = build_profile([self.seed], collection(self.seed))
        self.assertIsNone(best_match(game(2, themes=[]), self.profile))
        self.assertIsNone(best_match(game(2, themes=[{"id": 1, "name": "Action"}]), self.profile))
        self.assertIsNone(best_match(game(2, genres=None, themes=None), self.profile))
        generic = game(1, genres=[{"id": 31, "name": "Adventure"}])
        profile = build_profile([generic], collection(generic))
        self.assertIsNone(best_match(game(2, genres=generic["genres"]), profile))

    def test_reason_uses_the_closest_favorite_and_only_shared_terms(self):
        other = game(3, "Fantasy RPG", themes=[{"id": 17, "name": "Fantasy"}])
        profile = build_profile([other, self.seed], collection(other, self.seed))
        candidate = game(5, "Fantasy candidate", themes=other["themes"])
        match = best_match(candidate, profile)
        self.assertEqual(match.source_id, 3)
        self.assertIn("Fantasy RPG", match.reason)
        self.assertIn("Fantasy", match.reason)
        self.assertIn("First person", match.reason)
        self.assertNotIn("Science fiction", match.reason)
        self.assertNotIn("Future RPG", match.reason)

    def test_unrelated_favorites_cannot_combine_into_a_fake_match(self):
        other = game(3, genres=[{"id": 5, "name": "Shooter"}],
                     themes=[{"id": 17, "name": "Fantasy"}])
        profile = build_profile([self.seed, other], collection(self.seed, other))
        self.assertIsNone(best_match(game(5, themes=other["themes"]), profile))

    def test_two_gameplay_keywords_can_support_a_match_without_themes(self):
        keywords = [{"id": 1, "name": "stealth"}, {"id": 2, "name": "branching dialogue"}]
        seed = game(1, keywords=keywords, themes=[])
        profile = build_profile([seed], collection(seed))
        match = best_match(game(2, keywords=keywords, themes=[]), profile)
        self.assertIsNotNone(match)
        self.assertIn("branching dialogue", match.reason)
        self.assertIsNone(best_match(game(2, keywords=keywords[:1], themes=[]), profile))

    def test_platform_metadata_keywords_do_not_count_as_gameplay(self):
        keywords = [{"id": 1, "name": "steam"}, {"id": 2, "name": "achievements"}]
        seed = game(1, keywords=keywords, themes=[])
        profile = build_profile([seed], collection(seed))
        self.assertIsNone(best_match(game(2, keywords=keywords, themes=[]), profile))

    def test_refresh_keeps_strong_repeat_above_weaker_new_match(self):
        strong = game(2, "Strong")
        weaker = game(3, "Weaker", player_perspectives=[])
        for value in range(20):
            result = select_recommendations({"PC": [weaker, strong]}, [], self.profile,
                                            [2], limit=1, rng=random.Random(value))
            self.assertEqual(result[0]["igdb_id"], 2)

    def test_refresh_rotates_equally_good_matches(self):
        result = select_recommendations({"PC": [game(2, "Old"), game(3, "New")]}, [],
                                        self.profile, [2], limit=1, rng=random.Random(0))
        self.assertEqual(result[0]["igdb_id"], 3)

    def test_variety_never_adds_unqualified_platform_or_fills_twenty(self):
        pools = {"PC": [game(2, "PC")], "PS1": [game(3, "PS1", "PS1")],
                 "GBA": [game(4, "Weak", "GBA", themes=[])]}
        result = select_recommendations(pools, [], self.profile)
        self.assertEqual({g["platform"] for g in result}, {"PC", "PS1"})
        self.assertEqual(len(result), 2)

    def test_diversity_does_not_reserve_a_slot_far_below_best_affinity(self):
        keywords = [{"id": 1, "name": "stealth"}, {"id": 2, "name": "branching dialogue"},
                    {"id": 3, "name": "cybernetics"}]
        seed = game(1, keywords=keywords)
        profile = build_profile([seed], collection(seed))
        strong = game(2, "Strong", keywords=keywords)
        weak = game(3, "Only broad resemblance", "GBA", player_perspectives=[])
        self.assertIsNotNone(best_match(weak, profile))
        result = select_recommendations({"PC": [strong], "GBA": [weak]}, [], profile)
        self.assertEqual([g["igdb_id"] for g in result], [2])

    def test_incidental_keyword_is_not_advertised_in_explanation(self):
        keyword = [{"id": 90, "name": "licensed game"}]
        seed = game(1, keywords=keyword)
        match = best_match(game(2, keywords=keyword), build_profile([seed], collection(seed)))
        self.assertNotIn("licensed game", match.reason)

    def test_unknown_metadata_and_same_name_different_ids_are_not_evidence(self):
        self.assertIsNone(best_match(game(2, genres=[12], themes=[18]),
                                    build_profile([game(1, genres=[12], themes=[18])], collection(self.seed))))
        self.assertIsNone(best_match(game(2, themes=[{"id": 999, "name": "Science fiction"}]), self.profile))

    def test_many_other_favorites_do_not_outvote_best_match(self):
        before = best_match(game(2), self.profile)
        others = [game(i, themes=[{"id": 17, "name": "Fantasy"}]) for i in range(10, 110)]
        after = best_match(game(2), build_profile([self.seed, *others], collection(self.seed, *others)))
        self.assertEqual(before, after)

    def test_filters_require_two_dimensions(self):
        clauses = candidate_filters(self.profile)
        self.assertTrue(clauses)
        self.assertTrue(all("genres =" in clause and " & " in clause for clause in clauses))

    def test_cache_version_invalidates_old_matches_without_deleting_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cover = root / "assets/recommendations/test.jpg"
            cover.parent.mkdir(parents=True)
            cover.write_bytes(b"cover")
            suggestion = dict(game(2), igdb_id=2, platform="PC", status="recommended",
                              cover_path=cover, reason=best_match(game(2), self.profile).reason)
            save_recommendations(root, [suggestion], collection(self.seed))
            self.assertEqual(load_recommendations(root, collection(self.seed))[0]["reason"], suggestion["reason"])
            cache = root / "data/recommendations.json"
            old = json.loads(cache.read_text())
            old.pop("version")
            cache.write_text(json.dumps(old))
            before = cache.read_bytes()
            self.assertEqual(load_recommendations(root, collection(self.seed)), [])
            self.assertEqual(cache.read_bytes(), before)
            self.assertTrue(cover.exists())

    def fetch(self, responses, download=None):
        with tempfile.TemporaryDirectory() as folder, \
             patch("retro_beaten.services.recommendations.load_credentials", return_value=("id", "secret")), \
             patch("retro_beaten.services.recommendations.get_access_token", return_value="token"), \
             patch("retro_beaten.services.recommendations.query_games", side_effect=responses) as query, \
             patch("retro_beaten.services.recommendations.download_cover", return_value=Path(folder)/"cover.jpg",
                   side_effect=download):
            result = fetch_recommendations(collection(self.seed), [], folder)
            return result, query.call_args_list

    def test_fetch_accepts_single_platform_and_empty_qualified_pool(self):
        pools = [[game(2)] if code == "PC" else [] for code in PLATFORMS]
        result, calls = self.fetch([[self.seed], *pools])
        self.assertEqual(len(result), 1)
        self.assertTrue(all("themes.name" in call.args[2] for call in calls))
        result, _ = self.fetch([[self.seed], *[[] for _ in PLATFORMS]])
        self.assertEqual(result, [])

    def test_explicit_similar_games_are_fetched_and_still_checked(self):
        self.seed["similar_games"] = [2, 3]
        result, calls = self.fetch([[self.seed], [game(2, "Close"), game(3, "Unrelated", themes=[])],
                                    *[[] for _ in PLATFORMS]])
        self.assertEqual([g["igdb_id"] for g in result], [2])
        self.assertIn("id = (2,3)", calls[1].args[2])
        self.assertIn("linked as similar", result[0]["reason"])

    def test_failed_cover_downloads_do_not_replace_old_list_with_empty_success(self):
        pools = [[game(2)] if code == "PC" else [] for code in PLATFORMS]
        with self.assertRaisesRegex(ValueError, "Previous recommendations were kept"):
            self.fetch([[self.seed], *pools], download=OSError("offline"))
