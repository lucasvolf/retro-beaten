"""Recommendations based on Beaten games, balanced across platforms."""

import json
from pathlib import Path
import random
import time

from retro_beaten.services.igdb_api import load_credentials, get_access_token, query_games, download_cover
from retro_beaten.library import normalize_name
from retro_beaten.platforms import PLATFORMS
from retro_beaten.services.recommendation_matching import (
    FEATURE_FIELDS, MIN_AFFINITY, best_match, build_profile, candidate_filters,
)

CACHE_VERSION = 2


def exclude_collection(candidates, collection):
    """Exclude games already in the collection, including other platform versions."""
    ids = {game.get("igdb_id") for game in collection if game.get("igdb_id")}
    names = {normalize_name(game["name"]) for game in collection}
    return [game for game in candidates
            if game.get("igdb_id", game["id"]) not in ids
            and normalize_name(game["name"]) not in names]


def select_recommendations(pools, collection, profile, previous_ids=(), limit=20, rng=None):
    """Select one recommendation per platform each round, without duplicate games."""
    rng = rng or random.Random()
    previous_ids = set(previous_ids)
    ranked = {}
    matches = {}
    for platform, candidates in pools.items():
        options = []
        for game in exclude_collection(candidates, collection):
            if not (game.get("cover") or {}).get("image_id"):
                continue
            if PLATFORMS[platform]["igdb_id"] not in {
                item["id"] for item in game.get("platforms", [])
            }:
                continue
            if game["id"] not in matches:
                matches[game["id"]] = best_match(game, profile)
            match = matches[game["id"]]
            if match is None:
                continue
            # Novelty is a small tie-breaker among close matches, never the first key.
            score = match.score - (0.2 if game["id"] in previous_ids else 0) + rng.random() * 0.1
            options.append((-score, game["id"], game, match.reason, match.score))
        options.sort(key=lambda option: option[:2])
        ranked[platform] = options

    # Diversity never fills a platform with much weaker matches. Compare raw
    # affinity here so refresh/randomness cannot change the quality threshold.
    strongest = max((option[4] for options in ranked.values() for option in options), default=0)
    floor = max(MIN_AFFINITY, strongest * .65)
    ranked = {code: [option for option in options if option[4] >= floor]
              for code, options in ranked.items()}

    # Platforms with fewer qualified candidates choose first to preserve variety.
    order = list(ranked)
    rng.shuffle(order)
    order.sort(key=lambda code: len(ranked[code]))
    selected, used_ids, used_names = [], set(), set()
    while len(selected) < limit:
        added = False
        for platform in order:
            while ranked[platform]:
                _, _, game, reason, _ = ranked[platform].pop(0)
                name = normalize_name(game["name"])
                if game["id"] in used_ids or name in used_names:
                    continue
                selected.append({
                    **game, "id": f"recommended:{game['id']}:{platform}",
                    "igdb_id": game["id"], "platform": platform,
                    "status": "recommended", "reason": reason,
                })
                used_ids.add(game["id"])
                used_names.add(name)
                added = True
                break
            if len(selected) >= limit:
                break
        if not added:
            break
    return selected


def fetch_recommendations(collection, previous_ids, project_dir, progress=lambda text: None):
    """Query IGDB and prepare covers without modifying the personal collection."""
    ids = sorted({int(g["igdb_id"]) for g in collection
                  if g["status"] == "beaten" and g.get("favorite") and g.get("igdb_id")})
    if not ids:
        raise ValueError("Star at least one Beaten game added through IGDB to get recommendations. Manual games can be favorites, but cannot be used as IGDB references.")
    progress("Looking up your favorite Beaten games on IGDB...")
    client_id, secret = load_credentials()
    token = get_access_token(client_id, secret)
    seeds = []
    for start in range(0, len(ids), 100):
        batch = ",".join(map(str, ids[start:start + 100]))
        seeds.extend(query_games(client_id, token,
            f"fields name, {FEATURE_FIELDS}, similar_games; where id = ({batch}); limit 100;"))
    profile = build_profile(seeds, collection)
    filters = candidate_filters(profile)
    related_ids = sorted({game_id for seed in profile for game_id in seed.related})
    if not filters and not related_ids:
        raise ValueError("IGDB has too little matching information for your favorite Beaten games yet.")
    fields = f"name, summary, {FEATURE_FIELDS}, similar_games, platforms.name, cover.image_id, total_rating"
    available = (f"cover != null & first_release_date < {int(time.time())} "
                 "& parent_game = null & version_parent = null")
    pools = {code: [] for code in PLATFORMS}
    # Fetch explicit related games separately so rating-sorted genre queries cannot hide them.
    for start in range(0, len(related_ids), 100):
        batch = ",".join(map(str, related_ids[start:start + 100]))
        related = query_games(client_id, token,
            f"fields {fields}; where id = ({batch}) & {available}; limit 100;")
        for code, platform in PLATFORMS.items():
            pools[code].extend(game for game in related if platform["igdb_id"] in
                              {item["id"] for item in game.get("platforms", [])})
    if filters:
        for code, platform in PLATFORMS.items():
            progress(f"Finding close matches for {platform['name']}...")
            pools[code].extend(query_games(client_id, token, f"""
                fields {fields};
                where platforms = ({platform['igdb_id']}) & {available}
                    & ({' | '.join(filters)});
                sort total_rating desc;
                limit 200;
            """))
    # The same game can occur in related and metadata queries.
    pools = {code: list({g["id"]: g for g in games}.values()) for code, games in pools.items()}
    suggestions = select_recommendations(pools, collection, profile, previous_ids)
    prepared = []
    for index, game in enumerate(suggestions, 1):
        progress(f"Loading covers: {index}/{len(suggestions)}...")
        try:
            path = download_cover(
                {**game, "id": game["igdb_id"]}, Path(project_dir) / "assets" / "recommendations"
            )
        except (OSError, ValueError):
            continue
        prepared.append({**game, "cover_path": path})
    if suggestions and not prepared:
        raise ValueError("Could not download recommendation covers. Previous recommendations were kept.")
    return prepared


def save_recommendations(project_dir, games, collection=()):
    """Replace the cache only after the new list is ready."""
    project_dir = Path(project_dir).resolve()
    path = project_dir / "data" / "recommendations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{**game, "cover_path": Path(game["cover_path"]).resolve().relative_to(project_dir).as_posix()}
               for game in games]
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps({"version": CACHE_VERSION, "favorite_seeds": recommendation_seeds(collection), "games": records}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_recommendations(project_dir, collection):
    """Load the latest recommendations offline; ignore an invalid or incomplete cache."""
    project_dir = Path(project_dir).resolve()
    try:
        cached = json.loads((project_dir / "data/recommendations.json").read_text(encoding="utf-8"))
        if (not isinstance(cached, dict) or cached.get("version") != CACHE_VERSION
                or cached.get("favorite_seeds") != recommendation_seeds(collection)):
            return []
        records = cached["games"]
        games = []
        for record in records:
            path = (project_dir / record["cover_path"]).resolve()
            if (not path.is_relative_to(project_dir / "assets/recommendations")
                    or not path.is_file() or record["platform"] not in PLATFORMS
                    or record["status"] != "recommended"):
                continue
            # Older caches may contain app-generated reasons in another language.
            if "reason" in record:
                reason = record["reason"]
                if not isinstance(reason, str) or not reason.startswith((
                    "Related to ", "Based on ",
                )):
                    record = {**record, "reason": "Based on your favorite Beaten collection."}
            games.append({**record, "cover_path": path})
        return exclude_collection(games, collection)
    except (OSError, ValueError, TypeError, KeyError):
        return []


def recommendation_seeds(collection):
    """Stable identity for the favorites used by a cached or in-flight query."""
    return sorted({f"{game['platform']}:{game['igdb_id']}" for game in collection
                   if game["status"] == "beaten" and game.get("favorite") and game.get("igdb_id")})
