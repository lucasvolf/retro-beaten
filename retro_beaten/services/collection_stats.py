"""Read-only counts of saved games, independent of the visible shelf filter."""

from collections import Counter
from retro_beaten.statuses import STATUS_LABELS


def collection_stats(games):
    saved = [game for game in games if game["status"] in STATUS_LABELS]
    statuses = {status: 0 for status in STATUS_LABELS}
    platforms = {}
    favorites = 0
    for game in saved:
        status = game["status"]
        statuses[status] += 1
        platforms.setdefault(game["platform"], Counter())[status] += 1
        favorites += bool(game.get("favorite"))
    return {"total": len(saved), "statuses": statuses, "platforms": platforms, "favorites": favorites}
