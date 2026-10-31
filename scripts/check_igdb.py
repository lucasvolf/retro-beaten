"""Manually test IGDB functions without adding games to the collection."""

from urllib.error import HTTPError, URLError

from retro_beaten.paths import PROJECT_DIR

from retro_beaten.services.igdb_api import load_credentials, get_access_token, search_games, download_cover


def main():
    try:
        client_id, client_secret = load_credentials()
    except ValueError as error:
        print(error)
        return 1

    service = "Twitch"
    try:
        print("Requesting authorization from Twitch...")
        access_token = get_access_token(client_id, client_secret)
        print("Authentication OK! Searching for Tekken 3 on PlayStation 1...")

        service = "IGDB"
        # 7 is the IGDB platform ID for the original PlayStation.
        games = search_games(client_id, access_token, "Tekken 3", platform_id=7)
    except HTTPError as error:
        print(f"{service} returned HTTP error {error.code}.")
        if error.code == 400 and service == "IGDB":
            print("IGDB rejected the query. Check its syntax.")
        elif error.code in (400, 401, 403):
            print("Check the Client ID and current secret for the same application.")
        elif error.code == 429:
            print("Too many requests. Wait a moment before retrying.")
        else:
            print("The service did not complete the request. Try again later.")
        return 1
    except (URLError, TimeoutError):
        print("Could not connect. Check your internet connection.")
        return 1
    except (ValueError, UnicodeError):
        print(f"{service} did not return data in the expected format.")
        return 1

    if not games:
        print("No games found for this name and platform.")
        return 0

    for game in games:
        platforms = ", ".join(
            platform["name"] for platform in game.get("platforms", [])
        )
        cover_url = game.get("cover", {}).get("url", "")
        if cover_url.startswith("//"):
            cover_url = "https:" + cover_url

        print()
        print("IGDB ID:", game.get("id"))
        print("Name:", game.get("name", "Not provided"))
        print("Available platforms:", platforms or "Not provided")
        print("Cover:", cover_url or "Unavailable")
        print("Description:", game.get("summary") or "Unavailable")

    # This diagnostic downloads only the verified PS1 version.
    selected_game = next((game for game in games if game.get("id") == 306134), None)
    if selected_game is None:
        print("\nThe expected record was not found. No cover was downloaded.")
        return 1

    print("\nDownloading the Tekken 3 cover...")
    previews_dir = PROJECT_DIR / "assets" / "previews"
    try:
        cover_path = download_cover(selected_game, previews_dir)
    except HTTPError as error:
        print(f"Could not download the cover: HTTP {error.code}.")
        return 1
    except (URLError, TimeoutError):
        print("Connection failed during download. Please try again.")
        return 1
    except (OSError, ValueError):
        print("Could not validate or save the cover image.")
        return 1

    print("Cover saved to:", cover_path)
    print("The database has not been changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
