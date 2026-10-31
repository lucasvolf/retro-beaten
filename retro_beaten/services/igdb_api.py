"""IGDB authentication, game search, and cover downloads.

Importing this module does not make requests or read credentials.
Operations run only when the corresponding functions are called.
"""

import json
import os
import time
from threading import Lock
from io import BytesIO
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from PIL import Image
from dotenv import load_dotenv

from retro_beaten.paths import get_data_dir


_request_lock = Lock()
_last_request = 0.0


def load_credentials():
    """Read local credentials without printing them."""
    env_path = get_data_dir() / ".env"
    load_dotenv(env_path, override=True, encoding="utf-8-sig", interpolate=False)
    client_id = os.getenv("IGDB_CLIENT_ID", "").strip()
    client_secret = os.getenv("IGDB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError("Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in your .env file.")
    return client_id, client_secret


def get_access_token(client_id, client_secret):
    """Exchange credentials for a temporary Twitch access token."""
    # Send credentials as form data in the request body.
    form_data = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }).encode("utf-8")

    request = Request(
        "https://id.twitch.tv/oauth2/token",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )

    with urlopen(request, timeout=15) as response:
        data = json.load(response)

    if not isinstance(data, dict) or not data.get("access_token"):
        raise ValueError("The response does not contain the expected token.")
    return data["access_token"]


def search_games(client_id, access_token, game_name, platform_id):
    """Search games by name, filtered by the IGDB platform ID."""
    # json.dumps quotes the name and escapes any embedded quotes.
    query = f'''
        search {json.dumps(game_name)};
        fields name, platforms.name, cover.url, cover.image_id, summary;
        where platforms = ({int(platform_id)});
        limit 5;
    '''
    return query_games(client_id, access_token, query)


def query_games(client_id, access_token, query):
    """Query games while spacing requests from application threads."""
    global _last_request
    # Limit this process to roughly three request starts per second.
    with _request_lock:
        wait = 0.35 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    request = Request(
        "https://api.igdb.com/v4/games",
        data=query.encode("utf-8"),
        headers={
            "Client-ID": client_id,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "text/plain"
        },
        method="POST"
    )
    with urlopen(request, timeout=15) as response:
        games = json.load(response)

    if not isinstance(games, list) or any(not isinstance(game, dict) for game in games):
        raise ValueError("The response does not contain the expected game list.")
    return games


def download_cover(game, destination_dir):
    """Download a larger cover and return its local path."""
    image_id = (game.get("cover") or {}).get("image_id")
    if not image_id:
        raise ValueError("This game has no available cover.")

    image_url = (
        "https://images.igdb.com/igdb/image/upload/"
        f"t_cover_big_2x/{quote(image_id, safe='')}.jpg"
    )
    # Public images do not require the search access token.
    with urlopen(image_url, timeout=15) as response:
        image_data = response.read()

    # Pillow validates the response image before writing the file.
    with Image.open(BytesIO(image_data)) as image:
        if image.format != "JPEG":
            raise ValueError("The response does not contain the expected JPEG image.")
        image.verify()

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"igdb_{int(game['id'])}.jpg"
    destination.write_bytes(image_data)
    return destination
