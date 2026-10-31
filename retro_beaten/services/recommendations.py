"""Recommendations based on Beaten games, balanced across platforms."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import time

from retro_beaten.services.igdb_api import load_credentials, get_access_token, query_games, download_cover
from retro_beaten.library import normalize_name
from retro_beaten.platforms import PLATFORMS


def exclude_collection(candidates, collection):
    """Exclude games already in the collection, including other platform versions."""
    ids = {game.get("igdb_id") for game in collection if game.get("igdb_id")}
    names = {normalize_name(game["name"]) for game in collection}
    return [game for game in candidates
            if game.get("igdb_id", game["id"]) not in ids
            and normalize_name(game["name"]) not in names]


def build_profile(seeds, collection):
    """Give each platform equal weight, even with many Beaten PC games."""
    by_id = {game["id"]: game for game in seeds}
    groups = defaultdict(set)
    for game in collection:
        if game["status"] == "beaten" and game.get("igdb_id") in by_id:
            groups[game["platform"]].add(game["igdb_id"])
    genres = Counter()
    similar = {}
    genre_sources = {}
    for ids in groups.values():
        for game_id in sorted(ids):
            seed = by_id[game_id]
            seed_genres = seed.get("genres") or []
            for genre in seed_genres:
                genres[genre] += 1 / len(ids) / len(seed_genres)
                genre_sources.setdefault(genre, seed["name"])
            for related_id in seed.get("similar_games") or []:
                similar.setdefault(related_id, seed["name"])
    return genres, similar, genre_sources


def select_recommendations(pools, collection, profile, previous_ids=(), limit=12, rng=None):
    """Select one recommendation per platform each round, without duplicate games."""
    rng = rng or random.Random()
    genres, similar, genre_sources = profile
    previous_ids = set(previous_ids)
    ranked = {}
    for platform, candidates in pools.items():
        options = []
        for game in exclude_collection(candidates, collection):
            if not (game.get("cover") or {}).get("image_id"):
                continue
            if PLATFORMS[platform]["igdb_id"] not in {
                item["id"] for item in game.get("platforms", [])
            }:
                continue
            common = [genre for genre in game.get("genres", []) if genre in genres]
            if game["id"] not in similar and not common:
                continue
            score = sum(genres[g] for g in common) + (3 if game["id"] in similar else 0)
            if game["id"] in similar:
                reason = f"Related to {similar[game['id']]} on IGDB, one of your Beaten games."
            else:
                source = genre_sources[max(common, key=genres.get)]
                reason = f"Shares a genre with {source}, one of your Beaten games."
            options.append((game["id"] in previous_ids, -score + rng.random() * 0.5, game, reason))
        options.sort(key=lambda option: option[:2])
        ranked[platform] = options

    # Platforms with fewer candidates choose first to preserve variety.
    order = list(ranked)
    rng.shuffle(order)
    order.sort(key=lambda code: len(ranked[code]))
    selected, used_ids, used_names = [], set(), set()
    while len(selected) < limit:
        added = False
        for platform in order:
            while ranked[platform]:
                _, _, game, reason = ranked[platform].pop(0)
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
                  if g["status"] == "beaten" and g.get("igdb_id")})
    if not ids:
        raise ValueError("Add at least one Beaten game through IGDB to get recommendations.")
    progress("Looking up your Beaten games on IGDB...")
    client_id, secret = load_credentials()
    token = get_access_token(client_id, secret)
    seeds = []
    for start in range(0, len(ids), 100):
        batch = ",".join(map(str, ids[start:start + 100]))
        seeds.extend(query_games(client_id, token,
            f"fields name, genres, similar_games; where id = ({batch}); limit 100;"))
    profile = build_profile(seeds, collection)
    genres, similar, _ = profile
    filters = []
    if genres:
        filters.append("genres = (" + ",".join(str(g) for g, _ in genres.most_common(12)) + ")")
    if similar:
        filters.append("id = (" + ",".join(map(str, sorted(similar))) + ")")
    if not filters:
        raise ValueError("IGDB has not returned genres or similar games for your Beaten collection yet.")
    pools = {}
    for code, platform in PLATFORMS.items():
        progress(f"Finding recommendations for {platform['name']}...")
        pools[code] = query_games(client_id, token, f"""
            fields name, summary, genres, platforms.name, cover.image_id, total_rating;
            where platforms = ({platform['igdb_id']}) & cover != null
                & first_release_date < {int(time.time())}
                & parent_game = null & version_parent = null
                & ({' | '.join(filters)});
            sort total_rating desc;
            limit 100;
        """)
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
    if len({game["platform"] for game in prepared}) < 2:
        raise ValueError("Could not prepare recommendations across platforms. Please refresh again.")
    return prepared


def save_recommendations(project_dir, games):
    """Replace the cache only after the new list is ready."""
    project_dir = Path(project_dir).resolve()
    path = project_dir / "data" / "recommendations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{**game, "cover_path": Path(game["cover_path"]).resolve().relative_to(project_dir).as_posix()}
               for game in games]
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_recommendations(project_dir, collection):
    """Load the latest recommendations offline; ignore an invalid or incomplete cache."""
    project_dir = Path(project_dir).resolve()
    try:
        records = json.loads((project_dir / "data/recommendations.json").read_text(encoding="utf-8"))
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
                    "Related to ", "Shares a genre with ", "Based on your Beaten collection.",
                )):
                    record = {**record, "reason": "Based on your Beaten collection."}
            games.append({**record, "cover_path": path})
        return exclude_collection(games, collection)
    except (OSError, ValueError, TypeError, KeyError):
        return []
