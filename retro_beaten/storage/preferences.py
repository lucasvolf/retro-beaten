"""Validated local display preferences, independent of collection records."""

import json

COVER_SIZES = {"Small": (105, 140), "Medium": (150, 200), "Large": (210, 280)}
SORT_ORDERS = ("Name A-Z", "Name Z-A", "Recently added")


def load_preferences(path):
    defaults = {"cover_size": "Medium", "sort_order": "Name A-Z", "sections": {}, "sidebar_expanded": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    if isinstance(data.get("cover_size"), str) and data["cover_size"] in COVER_SIZES:
        defaults["cover_size"] = data["cover_size"]
    if data.get("sort_order") in SORT_ORDERS:
        defaults["sort_order"] = data["sort_order"]
    if isinstance(data.get("sidebar_expanded"), bool):
        defaults["sidebar_expanded"] = data["sidebar_expanded"]
    if isinstance(data.get("sections"), dict):
        defaults["sections"] = {key: value for key, value in data["sections"].items()
                                if isinstance(value, bool)}
    if isinstance(data.get("section_order"), list):
        from retro_beaten.services.shelf_tools import section_order
        defaults["section_order"] = section_order([key for key in data["section_order"] if isinstance(key, str)])
    if isinstance(data.get("background_enabled"), bool):
        defaults["background_enabled"] = data["background_enabled"]
    darkness = data.get("background_darkness")
    if type(darkness) is int and 0 <= darkness <= 90:
        defaults["background_darkness"] = darkness
    return defaults


def save_preferences(path, preferences):
    """Replace the file only after the complete JSON has been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(preferences, indent=2), encoding="utf-8")
    temporary.replace(path)
