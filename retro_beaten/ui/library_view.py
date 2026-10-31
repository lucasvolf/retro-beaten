"""Collapsible sections and visual library layout."""

import customtkinter as ctk

from retro_beaten.library import filter_games
from retro_beaten.platforms import PLATFORMS
from retro_beaten.ui.cover_card import (
    COVER_SIZE, create_cover, attach_status_menu, attach_details_click,
)
from retro_beaten.ui.responsive_grid import enable_responsive_grid


def create_section(parent, title):
    """Create a collapsible section and return its cover panel."""
    section = ctk.CTkFrame(
        master=parent,
        fg_color="#1E293B"
    )
    section.pack(fill="x", padx=20, pady=(0, 20))

    is_expanded = True
    covers_frame = ctk.CTkFrame(
        master=section,
        fg_color="transparent"
    )

    def toggle_section():
        nonlocal is_expanded
        is_expanded = not is_expanded

        if is_expanded:
            # pack_forget does not retain options, so reuse the same margins.
            covers_frame.pack(fill="x", padx=20, pady=(0, 20))
            section_button.configure(text=f"▾  {title}")
        else:
            # Hide the panel without destroying its loaded covers.
            covers_frame.pack_forget()
            section_button.configure(text=f"▸  {title}")

    section_button = ctk.CTkButton(
        master=section,
        text=f"▾  {title}",
        font=("Segoe UI", 20, "bold"),
        text_color="#F8FAFC",
        fg_color="transparent",
        hover_color="#374151",
        anchor="w",
        height=40,
        border_spacing=10,
        command=toggle_section
    )
    section_button.pack(fill="x", padx=10, pady=10)
    covers_frame.pack(fill="x", padx=20, pady=(0, 20))

    return covers_frame


def create_library_area(parent):
    """Create the scrollable area containing the sections."""
    library_area = ctk.CTkScrollableFrame(
        master=parent,
        fg_color="#111827",
        orientation="vertical"
    )
    library_area.pack(
        fill="both",
        expand=True,
        padx=20,
        pady=(0, 20)
    )
    return library_area


def populate_section(parent, games, title, on_status_change, on_open_details):
    """Create a section with covers for the supplied games."""
    if not games:
        return

    covers_frame = create_section(parent, title)
    covers = []

    for game in games:
        cover_frame, cover_label = create_cover(
            parent=covers_frame,
            cover_path=game["cover_path"],
            size=COVER_SIZE,
            status=game["status"]
        )
        attach_status_menu(cover_frame, cover_label, game, on_status_change)
        attach_details_click(cover_frame, cover_label, game, on_open_details)
        covers.append(cover_frame)

    enable_responsive_grid(covers_frame, covers)


def render_library(parent, games, on_status_change, on_open_details, query="", recommendations=None):
    """Build personal shelves and the optional recommendations section."""
    # Filter only the displayed list; preserve the full collection.
    games = filter_games(games, query)
    if not games and not filter_games(recommendations or [], query):
        message = "No games found. Try another name or clear the search." if query.strip() else "Your collection is empty. Add a game to get started."
        ctk.CTkLabel(parent, text=message, text_color="#94A3B8", wraplength=560).pack(padx=20, pady=30)
        if recommendations is None or query.strip():
            return
    playing_games = [
        game for game in games
        if game["status"] == "playing"
    ]
    populate_section(
        parent, playing_games, "Playing", on_status_change, on_open_details
    )

    wishlist = [game for game in games if game["status"] == "wishlist"]
    populate_section(parent, wishlist, "Wishlist", on_status_change, on_open_details)
    if not wishlist and not query.strip() and recommendations is not None:
        empty_wishlist = create_section(parent, "Wishlist")
        ctk.CTkLabel(empty_wishlist, text="Keep the games you want to play here.",
                     text_color="#94A3B8").pack(pady=12)

    if recommendations is not None:
        suggested = filter_games(recommendations, query)
        if suggested:
            populate_section(parent, suggested, "Recommended", on_status_change, on_open_details)
        elif not query.strip():
            empty_recommended = create_section(parent, "Recommended")
            ctk.CTkLabel(empty_recommended,
                         text="Use Refresh recommendations to discover games based on your Beaten collection.",
                         text_color="#94A3B8").pack(pady=12)

    beaten_games = [
        game for game in games
        if game["status"] == "beaten"
    ]
    for platform_code in sorted(PLATFORMS):
        platform_games = [
            game for game in beaten_games
            if game["platform"] == platform_code
        ]
        platform_name = PLATFORMS[platform_code]["name"]
        populate_section(parent, platform_games, platform_name, on_status_change, on_open_details)

    dropped_games = [
        game for game in games
        if game["status"] == "dropped"
    ]
    populate_section(
        parent, dropped_games, "Dropped", on_status_change, on_open_details
    )
