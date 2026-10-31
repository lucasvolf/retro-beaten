"""Name search and legacy cover filename parsing."""

import unicodedata

from retro_beaten.platforms import PLATFORMS


def normalize_name(text):
    """Normalize names for comparison without accents, spaces, or punctuation."""
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(character for character in text if character.isalnum())


def filter_games(games, query):
    """Return matching games without changing the full collection."""
    query = normalize_name(query)
    return [game for game in games if query in normalize_name(game["name"])]


def load_games(images_dir):
    """Read cover filenames and return a list of game records."""
    games = []

    for image_path in sorted(images_dir.iterdir()):
        if not image_path.is_file():
            continue

        if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue

        platform_code, separator, game_name = image_path.stem.partition(" - ")
        platform_code = platform_code.strip().upper()
        game_name = game_name.strip()

        if not separator or platform_code not in PLATFORMS or not game_name:
            continue

        games.append({
            "name": game_name,
            "platform": platform_code,
            "cover_path": image_path,
            "status": "beaten"
        })

    return games
