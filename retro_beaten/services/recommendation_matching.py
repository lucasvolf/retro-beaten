"""Explainable, pairwise affinity. No network or personal-data access."""
from dataclasses import dataclass


FEATURE_FIELDS = "genres.name, themes.name, keywords.name, player_perspectives.name"
MIN_AFFINITY = 3.5
WEIGHTS = {"genres": 3.0, "themes": 2.0, "keywords": 3.0, "player_perspectives": 1.0}
LABELS = {"genres": "genres", "themes": "themes", "keywords": "characteristics",
          "player_perspectives": "perspective"}
# These labels convey little about the actual experience on their own.
BROAD = {"genres": {"adventure", "indie"}, "themes": {"action"},
         "keywords": {"single player", "single-player", "multiplayer", "steam",
                      "steam achievements", "achievements", "controller support",
                      "licensed game", "censored version", "year in the title", "nudity"}}


@dataclass
class Reference:
    id: int
    name: str
    features: dict
    related: set


@dataclass
class Match:
    score: float
    source_id: int
    reason: str


def terms(game, field):
    """Accept expanded IGDB records; keep IDs for comparison, names for explanations."""
    result = {}
    for item in game.get(field) or []:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            result[item["id"]] = str(item.get("name") or "")
        elif isinstance(item, int):
            result[item] = ""
    return result


def prepare(game):
    return Reference(game["id"], game["name"],
                     {field: terms(game, field) for field in WEIGHTS},
                     set(game.get("similar_games") or []))


def build_profile(seeds, collection):
    """Keep distinct eligible favorites; many PC favorites do not add repeated votes."""
    eligible = {g.get("igdb_id") for g in collection
                if g["status"] == "beaten" and g.get("favorite") and g.get("igdb_id")}
    unique = {g["id"]: prepare(g) for g in seeds if g["id"] in eligible}
    return tuple(unique[key] for key in sorted(unique))


def importance(field, name):
    if not name:
        return 0.0  # Unnamed metadata cannot support a useful explanation.
    if name.casefold() in BROAD.get(field, set()):
        return 0.0 if field == "keywords" else .15
    return 1.0


def compare(candidate, seed):
    """Score shared evidence against ONE favorite, never an aggregate of unrelated games."""
    score, evidence, shared = 0.0, [], {}
    for field, weight in WEIGHTS.items():
        left, right = candidate.features[field], seed.features[field]
        common = left.keys() & right.keys()
        names = {key: right.get(key) or left.get(key) for key in left.keys() | right.keys()}
        strength = {key: importance(field, name) for key, name in names.items()}
        informative = {key for key in common if strength[key] == 1.0}
        shared[field] = informative
        denominator = sum(strength[key] for key in left) + sum(strength[key] for key in right)
        if field == "keywords":
            # Keywords are unevenly catalogued: reward several concrete shared
            # traits without penalizing a game for having hundreds of other tags.
            score += weight * min(len(informative) / 3, 1.0)
        elif denominator:
            # Weighted Dice similarity penalizes unrelated genres/themes.
            score += (weight * 2 * sum(strength[key] for key in common) / denominator
                      * max((strength[key] for key in common), default=0))
        labels = sorted({names[key] for key in informative}, key=str.casefold)
        if labels:
            evidence.append(f"{LABELS[field]}: {', '.join(labels[:3])}")
    keywords = len(shared["keywords"]) >= 2
    common_genres = candidate.features["genres"].keys() & seed.features["genres"].keys()
    # Perspective or IGDB's related list alone cannot rescue a generic genre match.
    if not common_genres or not (shared["genres"] or keywords):
        return None
    if not (shared["themes"] or keywords):
        return None
    related = candidate.id in seed.related or seed.id in candidate.related
    if related:
        score += .75
    if score < MIN_AFFINITY:
        return None
    reason = f"Based on {seed.name}, one of your favorite Beaten games. Shared " + "; ".join(evidence) + "."
    if related:
        reason += " Also linked as similar on IGDB."
    return Match(score, seed.id, reason)


def best_match(game, profile):
    candidate = prepare(game)
    matches = [match for seed in profile if (match := compare(candidate, seed)) is not None]
    return max(matches, key=lambda match: (match.score, -match.source_id), default=None)


def candidate_filters(profile):
    """Use pairwise query clauses so popular games sharing only one genre cannot crowd the pool."""
    clauses = set()
    for seed in profile:
        genres = seed.features["genres"]
        if not genres:
            continue
        genre_filter = "genres = (" + ",".join(map(str, sorted(genres))) + ")"
        for field in ("themes", "keywords"):
            ids = [key for key, name in seed.features[field].items() if importance(field, name) == 1.0]
            if ids:
                clauses.add(f"({genre_filter} & {field} = ({','.join(map(str, sorted(ids)))}))")
    return sorted(clauses)
