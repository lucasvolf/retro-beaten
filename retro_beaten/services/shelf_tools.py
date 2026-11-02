"""Shelf grouping, local artwork, random picks, and shareable image exports."""

import math
import os
from pathlib import Path
import random
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont, ImageOps
from retro_beaten.platforms import PLATFORMS
from retro_beaten.library import sort_games
from retro_beaten.statuses import STATUS_BORDER_COLORS

SECTION_NAMES = {"playing": "Playing", "wishlist": "Wishlist", "recommended": "Recommended",
                 **{f"beaten:{code}": info["name"] for code, info in sorted(PLATFORMS.items())},
                 "dropped": "Dropped"}


def section_order(saved=()):
    return list(dict.fromkeys([key for key in saved if key in SECTION_NAMES] + list(SECTION_NAMES)))


def pick_wishlist(games, previous=None, rng=None):
    choices = [game for game in games if game["status"] == "wishlist"]
    if len(choices) > 1:
        choices = [game for game in choices if game["id"] != previous]
    return (rng or random).choice(choices) if choices else None


def save_background(source, project):
    destination = Path(project) / "data/background.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2560, 1440))
            image.save(temporary, format="PNG")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def font(size):
    try:
        return ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"), size)
    except OSError:
        return ImageFont.load_default(size=size)


class ExportCancelled(Exception):
    """The user cancelled before the destination was replaced."""


def export_shelf(games, destination, preferences, scope="Beaten only", *, progress=None, cancelled=None, temporary_path=None):
    """Render local covers to a PNG; never modify collection files."""
    def checkpoint():
        if cancelled is not None and cancelled():
            raise ExportCancelled("Export cancelled.")

    def report(done, total, text):
        if progress is not None:
            progress(done, total, text)

    checkpoint()
    selected = [game for game in games if scope != "Beaten only" or game["status"] == "beaten"]
    if not selected:
        raise ValueError("There are no games to export in this selection.")
    groups = []
    for key in section_order(preferences.get("section_order", [])):
        records = [game for game in selected if
                   (f"beaten:{game['platform']}" if game["status"] == "beaten" else game["status"]) == key]
        if records:
            groups.append((key, sort_games(records, preferences.get("sort_order", "Name A-Z"))))
    width, columns, cell, cover_size = 1600, 8, 188, (160, 214)
    height = 180 + sum(70 + math.ceil(len(records) / columns) * 244 for _, records in groups) + 40
    if width * height > 80_000_000:
        raise ValueError("This collection is too large for one image. Export Beaten only instead.")
    report(0, len(selected), "Preparing image...")
    canvas = Image.new("RGB", (width, height), "#101114")
    draw = ImageDraw.Draw(canvas)
    draw.text((48, 35), "RETRO BEATEN", font=font(44), fill="#E7B84B")
    draw.text((48, 98), "A Collection of Adventures, Not Achievements.", font=font(23), fill="#94A3B8")
    completed = 0
    heading_font, fallback_font = font(28), font(15)
    y = 180
    for key, records in groups:
        draw.text((48, y), SECTION_NAMES[key], font=heading_font, fill="#F8FAFC")
        y += 60
        for start in range(0, len(records), columns):
            row = records[start:start + columns]
            left = (width - len(row) * cell) // 2
            for index, game in enumerate(row):
                checkpoint()
                x = left + index * cell + (cell - cover_size[0]) // 2
                try:
                    with Image.open(game["cover_path"]) as image:
                        # JPEG draft decoding and thumbnail reduce memory before conversion.
                        image.draft("RGB", cover_size)
                        image.thumbnail(cover_size, Image.Resampling.LANCZOS, reducing_gap=3.0)
                        cover = image.convert("RGB")
                    px, py = x + (cover_size[0] - cover.width) // 2, y + (cover_size[1] - cover.height) // 2
                    canvas.paste(cover, (px, py))
                    draw.rectangle((px-3, py-3, px+cover.width+2, py+cover.height+2),
                                   outline=STATUS_BORDER_COLORS[game["status"]], width=3)
                except (OSError, ValueError):
                    draw.rectangle((x, y, x+160, y+214), fill="#191B20", outline="#363A43")
                    draw.text((x+12, y+90), "Cover unavailable", font=fallback_font, fill="#94A3B8")
                completed += 1
                report(completed, len(selected), f"Rendering covers: {completed}/{len(selected)}")
            y += 244
        y += 10
    destination = Path(destination)
    temporary = Path(temporary_path) if temporary_path is not None else destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        checkpoint()
        report(completed, len(selected), "Saving PNG...")
        canvas.save(temporary, format="PNG", compress_level=1)
        checkpoint()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination
