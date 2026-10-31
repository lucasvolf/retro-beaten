"""Stored collection statuses and shelf colors."""

STATUS_LABELS = {
    "beaten": "Beaten",
    "playing": "Playing",
    "wishlist": "Wishlist",
    "dropped": "Dropped",
}
STATUS_CODES = {label: code for code, label in STATUS_LABELS.items()}
STATUS_BORDER_COLORS = {
    "playing": "#3B82F6",
    "beaten": "#E7B84B",
    "wishlist": "#22C55E",
    "dropped": "#EF4444",
    "recommended": "#9CA3AF",
}
