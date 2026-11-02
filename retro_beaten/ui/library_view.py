"""Collapsible sections and visual library layout."""

import customtkinter as ctk
from time import perf_counter
from retro_beaten.ui.shelf_icons import shelf_icon
from retro_beaten.ui.favorite_star import add_favorite_star
from retro_beaten.ui.cover_hover import attach_cover_hover

from retro_beaten.library import filter_games, sort_games
from retro_beaten.platforms import PLATFORMS
from retro_beaten.ui.cover_card import (
    COVER_SIZE, create_cover, resize_cover, attach_status_menu, attach_details_click,
)
from retro_beaten.ui.cover_cache import cover_signature
from retro_beaten.ui.responsive_grid import enable_responsive_grid


def create_section(parent, title, expanded=True, on_toggle=None, on_expand=None, floating_header=False):
    """Create a collapsible section and return its cover panel."""
    section = ctk.CTkFrame(
        master=parent,
        fg_color="#191B20", border_width=1, border_color="#292C33", corner_radius=10
    )
    section.pack(fill="x", padx=20, pady=(0, 20))

    is_expanded = expanded
    covers_frame = ctk.CTkFrame(
        master=section,
        fg_color="transparent"
    )

    def toggle_section():
        nonlocal is_expanded
        is_expanded = not is_expanded
        root = section.winfo_toplevel()
        if hasattr(root, "_cover_tooltip"):
            root._cover_tooltip.hide()

        if is_expanded:
            if on_expand is not None:
                on_expand()
            # pack_forget does not retain options, so reuse the same margins.
            covers_frame.pack(fill="x", padx=20, pady=(0, 20))
            section_button.configure(text=f"▾  {title}")
        else:
            # Hide the panel without destroying its loaded covers.
            covers_frame.pack_forget()
            section_button.configure(text=f"▸  {title}")
        if hasattr(section, "_visibility_changed"):
            section._visibility_changed()
        if on_toggle is not None:
            on_toggle(is_expanded)

    header_parent = section
    if floating_header:
        # Keep the logical header space in the tall shelf, but draw the header
        # in viewport coordinates to avoid native Windows position clipping.
        header_parent = ctk.CTkFrame(parent._shelf_viewport.surface, height=71,
                                     fg_color="#191B20", corner_radius=10,
                                     border_width=1, border_color="#292C33")
        header_parent.pack_propagate(False)
        ctk.CTkFrame(section, height=71, fg_color="transparent").pack(fill="x")
        section._floating_header = header_parent

    section_button = ctk.CTkButton(
        master=header_parent,
        text=f"{chr(0x25be) if expanded else chr(0x25b8)}  {title}",
        font=("Segoe UI", 18, "bold"),
        image=shelf_icon(title), compound="left",
        text_color="#F1F2F4",
        fg_color="transparent",
        hover_color="#24272D",
        anchor="w",
        height=40,
        border_spacing=10,
        command=toggle_section
    )
    section_button.pack(fill="x", padx=12, pady=(10, 5))
    ctk.CTkFrame(header_parent, height=1, fg_color="#2D3037", corner_radius=0).pack(fill="x", padx=24, pady=(0, 8))
    if expanded:
        covers_frame.pack(fill="x", padx=20, pady=(0, 20))

    section._title_button = section_button
    section._set_expanded = lambda expanded: toggle_section() if is_expanded != expanded else None
    return covers_frame


def create_library_area(parent):
    """Create the scrollable area containing the sections."""
    library_area = ctk.CTkScrollableFrame(
        master=parent,
        fg_color="#101114",
        orientation="vertical"
    )
    library_area.pack(
        fill="both",
        expand=True,
        padx=8,
        pady=(0, 12)
    )
    return library_area


def populate_section(parent, games, title, on_status_change, on_open_details,
                     size=COVER_SIZE, expanded=True, on_toggle=None, exhibition=False, on_favorite_change=None, incremental=False):
    """Create a section with covers for the supplied games."""
    if not games:
        return

    if incremental and hasattr(parent, "_parent_canvas"):
        from retro_beaten.ui.virtual_shelf import create_virtual_section
        return create_virtual_section(parent, games, title, on_status_change, on_open_details,
                                      size, expanded, on_toggle, exhibition, on_favorite_change)

    loaded = False
    pending_render = None
    cards = {}
    current_games = games
    current_size = size
    current_exhibition = exhibition

    def load_covers():
        nonlocal loaded
        if loaded:
            return
        reconcile()
        loaded = True

    def cancel_render(event=None):
        nonlocal pending_render
        if pending_render is not None:
            covers_frame.after_cancel(pending_render)
            pending_render = None

    def build_card(game):
        signature = (id(game), game["name"], game["status"],
                     cover_signature(game["cover_path"]), current_size, current_exhibition)
        previous = cards.get(game["id"])
        if previous and previous[0] == signature:
            cover_frame = previous[1]
            if hasattr(cover_frame, "repaint_favorite"):
                cover_frame.repaint_favorite()
        elif previous and previous[0][:4] == signature[:4] and previous[0][5:] == signature[5:]:
            cover_frame = previous[1]
            resize_cover(cover_frame, game["cover_path"], current_size)
            cards[game["id"]] = (signature, cover_frame)
        else:
            if previous:
                previous[1].destroy()
            cover_frame, cover_label = create_cover(
                covers_frame, game["cover_path"], current_size, game["status"])
            if not current_exhibition:
                attach_status_menu(cover_frame, cover_label, game, on_status_change)
                attach_details_click(cover_frame, cover_label, game, on_open_details)
                attach_cover_hover(cover_frame, cover_label, game["name"],
                                   PLATFORMS.get(game["platform"], {}).get("name", game["platform"]))
            add_favorite_star(cover_frame, game, on_favorite_change, current_exhibition)
            cards[game["id"]] = (signature, cover_frame)
        return cover_frame

    def reconcile():
        nonlocal pending_render
        cancel_render()
        # Keep the panel geometry stable while cards are replaced in batches.
        # Otherwise each removal and insertion triggers a scrollable-area resize.
        covers_frame.grid_propagate(False)
        if getattr(covers_frame, "_cancel_cover_layout", None):
            covers_frame._cancel_cover_layout()
        wanted = {game["id"] for game in current_games}
        for key in list(cards):
            if key not in wanted:
                cards.pop(key)[1].destroy()
        records = iter(current_games)
        covers = []
        batched = incremental and len(current_games) > 32
        if batched:
            section._title_button.configure(text=f"{title}  ·  Loading covers...")
        section._rendering = True

        def step():
            nonlocal pending_render
            pending_render = None
            deadline = perf_counter() + 0.008
            while True:
                try:
                    game = next(records)
                except StopIteration:
                    section._rendering = False
                    # Preserve the current expanded/collapsed indicator.
                    arrow = "▾" if covers_frame.winfo_manager() else "▸"
                    section._title_button.configure(text=f"{arrow}  {title}")
                    enable_responsive_grid(covers_frame, covers)
                    covers_frame.grid_propagate(True)
                    return
                covers.append(build_card(game))
                if batched and perf_counter() >= deadline:
                    pending_render = covers_frame.after(5, step)
                    return
        step()

    def update_records(records, size, exhibition):
        nonlocal current_games, current_size, current_exhibition
        current_games, current_size, current_exhibition = records, size, exhibition
        if loaded:
            reconcile()

    covers_frame = create_section(parent, title, expanded, on_toggle, load_covers)
    section = covers_frame.master
    section._rendering = False
    section._cancel_render = cancel_render
    covers_frame._canvas.bind("<Destroy>", cancel_render, add="+")
    section._cards = cards
    section._covers_panel = covers_frame
    section._update_records = update_records
    if expanded:
        load_covers()
    return section


def render_library(parent, games, on_status_change, on_open_details, query="", recommendations=None,
                   preferences=None, on_section_toggle=None, exhibition=False, on_favorite_change=None, incremental=False, scope="all"):
    """Build personal shelves and the optional recommendations section."""
    from retro_beaten.storage.preferences import COVER_SIZES

    if incremental and hasattr(parent, "_parent_canvas"):
        from retro_beaten.ui.virtual_shelf import ShelfViewport
        if not hasattr(parent, "_shelf_viewport"):
            parent._shelf_viewport = ShelfViewport(parent)
        parent._shelf_viewport.set_empty_message()

    preferences = preferences or {"cover_size": "Medium", "sort_order": "Name A-Z", "sections": {}}

    def section_options(key):
        return {"expanded": preferences["sections"].get(key, True),
                "on_toggle": (lambda expanded: on_section_toggle(key, expanded))
                if on_section_toggle else None}

    cache = getattr(parent, "_shelf_cache", {})
    parent._shelf_cache = cache
    used = set()
    sections_by_key = {}
    for child in parent.winfo_children():
        if child not in [entry[1] for entry in cache.values()]:
            child.destroy()
        else:
            child.pack_forget()

    def populate(records, title, key, recommended=False):
        # Recommendations have remote IDs, so their original relevance order is
        # retained when the collection is ordered by most recent addition.
        order = preferences["sort_order"]
        if not (recommended and order == "Recently added"):
            records = sort_games(records, order)
        if not records:
            return
        used.add(key)
        signature = (preferences["cover_size"], exhibition, tuple(
            (id(game), game["id"], game["name"], game["status"],
             str(game["cover_path"]) if incremental else cover_signature(game["cover_path"]))
            for game in records))
        previous = cache.get(key)
        if previous and previous[0] == signature and previous[1].winfo_exists():
            if incremental:
                # The viewport checks file changes only for visible covers.
                previous[1]._update_records(records, COVER_SIZES[preferences["cover_size"]], exhibition)
            previous[1]._set_expanded(preferences["sections"].get(key, True))
            sections_by_key[key] = previous[1]
            previous[1].pack(fill="x", padx=20, pady=(0, 20))
            return
        if previous and previous[1].winfo_exists():
            section = previous[1]
            section._update_records(records, COVER_SIZES[preferences["cover_size"]], exhibition)
            section._set_expanded(preferences["sections"].get(key, True))
            section.pack(fill="x", padx=20, pady=(0, 20))
            cache[key] = (signature, section)
            sections_by_key[key] = section
            return
        section = populate_section(parent, records, title, on_status_change, on_open_details,
                                   size=COVER_SIZES[preferences["cover_size"]],
                                   exhibition=exhibition, on_favorite_change=on_favorite_change, incremental=incremental, **section_options(key))
        cache[key] = (signature, section)
        sections_by_key[key] = section

    def empty_section(title, key, message):
        if incremental and hasattr(parent, "_parent_canvas"):
            from retro_beaten.ui.virtual_shelf import create_virtual_section
            options = section_options(key)
            section = create_virtual_section(parent, [], title, on_status_change, on_open_details,
                                             COVER_SIZES[preferences["cover_size"]], options["expanded"],
                                             options["on_toggle"], exhibition, on_favorite_change)
            section._virtual_shelf.show_message(message)
        else:
            panel = create_section(parent, title, **section_options(key))
            section = panel.master
            ctk.CTkLabel(panel, text=message, text_color="#969BA5", wraplength=600).pack(pady=12)
        sections_by_key[key] = section

    # Navigation and search filter the view, never the saved collection.
    if scope != "all":
        games = [game for game in games if game["status"] == scope]
        if scope != "recommended":
            recommendations = None
    games = filter_games(games, query)
    if not games and not filter_games(recommendations or [], query):
        message = "No games found. Try another name or clear the search." if query.strip() else "Your collection is empty. Add a game to get started."
        if scope != "all" and not query.strip():
            message = "No games in this shelf yet."
        ctk.CTkLabel(parent, text=message, text_color="#969BA5", wraplength=560).pack(padx=20, pady=30)
        if incremental and hasattr(parent, "_shelf_viewport"):
            parent._shelf_viewport.set_empty_message(message)
        if recommendations is None or query.strip():
            for _, section in cache.values():
                section.destroy()
            cache.clear()
            return
    playing_games = [
        game for game in games
        if game["status"] == "playing"
    ]
    populate(playing_games, "Playing", "playing")

    wishlist = [game for game in games if game["status"] == "wishlist"]
    populate(wishlist, "Wishlist", "wishlist")
    if not wishlist and not query.strip() and recommendations is not None and scope == "all":
        empty_section("Wishlist", "wishlist", "Keep the games you want to play here.")

    if recommendations is not None:
        suggested = filter_games(recommendations, query)
        if suggested:
            populate(suggested, "Recommended", "recommended", recommended=True)
        elif not query.strip():
            empty_section("Recommended", "recommended",
                          "Use Refresh recommendations to discover games based on your favorite Beaten games. Star a Beaten game added through IGDB first.")

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
        populate(platform_games, platform_name, f"beaten:{platform_code}")

    dropped_games = [
        game for game in games
        if game["status"] == "dropped"
    ]
    populate(dropped_games, "Dropped", "dropped")

    for key in list(cache):
        if key not in used:
            cache.pop(key)[1].destroy()

    from retro_beaten.services.shelf_tools import section_order
    for section in sections_by_key.values():
        section.pack_forget()
    for key in section_order(preferences.get("section_order", [])):
        if key in sections_by_key:
            sections_by_key[key].pack(fill="x", padx=20, pady=(0, 20))


def update_favorite_display(parent, game):
    """Paint only the requested star, without decoding images or relaying the shelf."""
    for _, section in getattr(parent, "_shelf_cache", {}).values():
        entry = section._cards.get(game["id"])
        if entry and hasattr(entry[1], "repaint_favorite"):
            entry[1].repaint_favorite()


def clear_recommended_display(parent):
    """Invalidate suggestions without changing the geometry of personal shelves."""
    entry = getattr(parent, "_shelf_cache", {}).pop("recommended", None)
    if entry is None:
        return
    section = entry[1]
    panel = section._covers_panel
    if hasattr(section, "_virtual_shelf"):
        section._virtual_shelf.show_message("Favorites changed. Refresh recommendations to discover new games.")
        return
    section._update_records([], COVER_SIZE, False)
    if getattr(panel, "_cancel_cover_layout", None):
        panel._cancel_cover_layout()
    height = max(48, panel._reverse_widget_scaling(panel.winfo_height()))
    for child in panel.winfo_children():
        child.destroy()
    section._cards.clear()
    panel.configure(height=height)
    panel.pack_propagate(False)
    panel.grid_propagate(False)
    ctk.CTkLabel(panel, text="Favorites changed. Refresh recommendations to discover new games.",
                 text_color="#969BA5", wraplength=600).pack(fill="both", expand=True, pady=12)
