"""Coordinate the collection, windows, and interface actions."""

from pathlib import Path
import customtkinter as ctk
import sqlite3
from tkinter import messagebox, TclError

from retro_beaten.paths import get_data_dir
from retro_beaten.ui.theme import apply_theme
from retro_beaten.services.shelf_tools import pick_wishlist
from retro_beaten.ui.shelf_tools_window import ShelfToolsWindow
from retro_beaten.ui.overview_window import OverviewWindow
from retro_beaten.ui.background import Background
from retro_beaten.ui.drop_cover import enable_cover_drop
from retro_beaten.storage.preferences import load_preferences, save_preferences
from retro_beaten.ui.view_controls import ViewControls
from retro_beaten.statuses import STATUS_LABELS, STATUS_BORDER_COLORS
from retro_beaten.services.collection import (
    register_game, register_manual_game, replace_cover, delete_game, edit_game_details,
)
from retro_beaten.services.recommendations import (
    load_recommendations, save_recommendations, exclude_collection, recommendation_seeds,
)
from retro_beaten.storage.database import initialize_database, load_saved_games, update_game_status, update_game_favorite
from retro_beaten.ui.main_window import create_window
from retro_beaten.ui.sidebar import Sidebar, SHELVES
from retro_beaten.ui.library_view import create_library_area, render_library, update_favorite_display, clear_recommended_display
from retro_beaten.ui.library_search import LibrarySearch
from retro_beaten.ui.search_window import SearchWindow
from retro_beaten.ui.manual_game_window import ManualGameWindow
from retro_beaten.ui.details_window import DetailsWindow
from retro_beaten.ui.recommendation_controls import RecommendationControls
from retro_beaten.ui.backup_window import BackupWindow


class RetroBeatenApp:
    """Manage application state and connect windows to services."""

    def __init__(self, project_dir=None):
        # An explicit folder allows tests to run without touching the real collection.
        self.project_dir = Path(project_dir if project_dir is not None else get_data_dir()).resolve()
        self.database_path = self.project_dir / "data" / "retro_beaten.db"
        initialize_database(self.database_path)
        self.games = load_saved_games(self.database_path, self.project_dir)
        self.recommendations = load_recommendations(self.project_dir, self.games)

        self.preferences_path = self.project_dir / "data" / "preferences.json"
        self.preferences = load_preferences(self.preferences_path)
        self.exhibition = False
        self.shelf_scope = "all"
        apply_theme()
        self.window = create_window()
        self.search_window = None
        self.details_window = None
        self.manual_window = None
        self.backup_window = None
        self.tools_window = None
        self.overview_window = None
        self.last_wishlist_pick = None
        self.build_interface()
        self.refresh_library()

    def build_interface(self):
        """Connect each visual component to application actions."""
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(1, weight=1)
        self.sidebar = Sidebar(self.window, self.preferences.get("sidebar_expanded", True),
            self.remember_sidebar, self.select_shelf, self.open_search, self.open_manual,
            self.open_backup, self.open_shelf_tools, self.open_overview)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.content = ctk.CTkFrame(self.window, fg_color="#101114", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.header = ctk.CTkFrame(self.content, fg_color="transparent", corner_radius=0)
        self.header.pack(fill="x", padx=28, pady=(22, 18))
        heading = ctk.CTkFrame(self.header, fg_color="transparent")
        heading.pack(side="left", padx=(0, 20))
        self.library_title = ctk.CTkLabel(heading, text="All games", font=("Segoe UI", 25, "bold"), anchor="w")
        self.library_title.pack(anchor="w")
        self.library_subtitle = ctk.CTkLabel(heading, text="Your personal collection", font=("Segoe UI", 11),
                                           text_color="#969BA5", anchor="w")
        self.library_subtitle.pack(anchor="w")
        self.local_search = LibrarySearch(self.header, self.refresh_library, compact=True)
        self.local_search.pack(side="right", fill="x", expand=True, padx=(12, 0))
        self.shelf_toolbar = self.sidebar.settings
        self.recommendation_controls = RecommendationControls(
            self.shelf_toolbar, self.project_dir, lambda: self.games, lambda: self.recommendations,
            self.accept_recommendations, compact=True,
        )
        self.recommendation_controls.pack(fill="x", padx=4, pady=(0, 14))
        self.recommendation_controls.button.pack_configure(fill="x", expand=True)
        self.view_controls = ViewControls(
            self.shelf_toolbar, self.preferences, self.change_view, self.toggle_exhibition,
            on_pick=self.pick_next_game, vertical=True)
        self.view_controls.pack(fill="x")
        self.exhibition_bar = ctk.CTkFrame(self.content, fg_color="transparent")
        ctk.CTkLabel(self.exhibition_bar, text="RETRO BEATEN", text_color="#E7B84B",
                     font=("Segoe UI", 18, "bold")).pack(side="left")
        ctk.CTkButton(self.exhibition_bar, text="Exit exhibition (Esc)",
                      command=self.toggle_exhibition).pack(side="right")
        self.library_area = create_library_area(self.content)
        self.window.bind("<Escape>", self.exit_exhibition)
        self.background = Background(self.window, self.header, None)
        self.update_background()
        try:
            self.drop_handler = enable_cover_drop(self.window, self.open_dropped_cover)
        except (RuntimeError, TclError):
            self.drop_handler = None
            self.window.after(0, lambda: messagebox.showwarning(
                "Drag and drop", "Could not enable file drops. Use Add manually to choose a cover.", parent=self.window))

    def update_background(self):
        path = self.project_dir / "data/background.png" if self.preferences.get("background_enabled") else None
        self.background.load(path, self.preferences.get("background_darkness", 65))

    def open_shelf_tools(self):
        if self.tools_window is None or not self.tools_window.winfo_exists():
            self.tools_window = ShelfToolsWindow(self)
        else:
            self.focus_window(self.tools_window)

    def open_overview(self):
        if self.overview_window is None or not self.overview_window.winfo_exists():
            self.overview_window = OverviewWindow(self.window, lambda: self.games)
        else:
            self.overview_window.refresh()
            self.focus_window(self.overview_window)

    def pick_next_game(self):
        game = pick_wishlist(self.games, self.last_wishlist_pick)
        if game is None:
            messagebox.showinfo("What should I play?", "Add games to your Wishlist first.", parent=self.window)
            return
        self.last_wishlist_pick = game["id"]
        self.open_details(game)

    def open_dropped_cover(self, path):
        if self.manual_window is not None and self.manual_window.winfo_exists():
            if not messagebox.askyesno("Drop a cover", "Replace the cover in the open form?", parent=self.manual_window):
                return
        self.open_manual()
        self.manual_window.load_cover(path)
        self.focus_window(self.manual_window)

    def persist_preferences(self):
        try:
            save_preferences(self.preferences_path, self.preferences)
        except OSError as error:
            messagebox.showerror("Display preferences", f"Could not save preferences: {error}",
                                 parent=self.window)

    def change_view(self, key, value):
        self.preferences[key] = value
        self.persist_preferences()
        self.refresh_library()

    def remember_section(self, key, expanded):
        self.preferences["sections"][key] = expanded
        self.persist_preferences()

    def exit_exhibition(self, event=None):
        if self.exhibition:
            self.toggle_exhibition()

    def remember_sidebar(self, expanded):
        self.preferences["sidebar_expanded"] = expanded
        self.persist_preferences()
        self.background.schedule()

    def select_shelf(self, scope):
        if scope not in {key for key, _, _ in SHELVES}:
            return
        self.shelf_scope = scope
        self.refresh_library()

    def toggle_exhibition(self):
        self.exhibition = not self.exhibition
        library_container = self.library_area._parent_frame
        if self.exhibition:
            self.sidebar.grid_remove()
            self.header.pack_forget()
            self.exhibition_bar.pack(fill="x", padx=28, pady=12, before=library_container)
        else:
            self.exhibition_bar.pack_forget()
            self.sidebar.grid()
            self.header.pack(fill="x", padx=28, pady=(22, 18), before=library_container)
        self.background.schedule()
        self.refresh_library()

    def run(self):
        """Run the Tk event loop until the application closes."""
        self.window.mainloop()

    def open_details(self, game):
        if self.details_window is not None and self.details_window.winfo_exists():
            if self.details_window.game_id == game["id"]:
                self.focus_window(self.details_window)
                return
            self.details_window.destroy()
        recommended = game["status"] == "recommended"
        self.details_window = DetailsWindow(
            self.window, game, STATUS_BORDER_COLORS[game["status"]],
            on_wishlist=self.add_recommended if recommended else None,
            on_cover_change=self.change_cover if not recommended else None,
            on_delete=self.remove_game if not recommended else None,
            on_edit=self.edit_details if not recommended else None,
        )

    def open_search(self):
        if self.search_window is None or not self.search_window.winfo_exists():
            self.search_window = SearchWindow(self.window, self.add_game, self.project_dir)
        else:
            self.focus_window(self.search_window)

    def open_manual(self):
        if self.manual_window is None or not self.manual_window.winfo_exists():
            self.manual_window = ManualGameWindow(self.window, self.add_manual_game)
        else:
            self.focus_window(self.manual_window)

    @staticmethod
    def focus_window(window):
        """Focus an existing window."""
        window.deiconify()
        window.lift()
        window.focus_set()

    def open_backup(self):
        if self.backup_window is None or not self.backup_window.winfo_exists():
            self.backup_window = BackupWindow(
                self.window, self.database_path, self.project_dir, self.reload_collection,
            )
        else:
            self.focus_window(self.backup_window)

    def reload_collection(self):
        """Close stale forms and rebuild the shelf using the restored collection."""
        for attribute in ("details_window", "search_window", "manual_window"):
            window = getattr(self, attribute)
            if window is not None and window.winfo_exists():
                window.destroy()
            setattr(self, attribute, None)
        self.games = load_saved_games(self.database_path, self.project_dir)
        self.recommendations = load_recommendations(self.project_dir, self.games)
        self.local_search.clear()
        self.refresh_library()

    def add_game(self, game, platform, status, preview_path):
        record = register_game(
            self.database_path, self.project_dir, game, platform, status, preview_path,
        )
        self.show_added_game(record)

    def add_manual_game(self, name, platform, status, cover_path, summary):
        record = register_manual_game(
            self.database_path, self.project_dir, name, platform, status, cover_path, summary,
        )
        self.show_added_game(record)

    def add_recommended(self, game):
        try:
            record = register_game(
                self.database_path, self.project_dir, {**game, "id": game["igdb_id"]},
                game["platform"], "wishlist", game["cover_path"],
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Wishlist", str(error), parent=self.window)
            return
        if self.details_window is not None and self.details_window.winfo_exists():
            self.details_window.destroy()
            self.details_window = None
        self.show_added_game(record)

    def show_added_game(self, record):
        if self.shelf_scope not in ("all", record["status"]):
            self.shelf_scope = record["status"]
        self.games.append(record)
        self.games.sort(key=lambda item: item["name"].casefold())
        self.recommendations = exclude_collection(self.recommendations, self.games)
        # Show the new game even if a previous search would hide it.
        self.local_search.clear()
        self.refresh_library()

    def change_cover(self, game, image_data):
        game["cover_path"] = replace_cover(self.database_path, self.project_dir, game, image_data)
        if self.details_window is not None and self.details_window.winfo_exists():
            if self.details_window.game_id == game["id"]:
                self.details_window.show_cover(game["cover_path"])
        self.window.after_idle(self.refresh_library)

    def edit_details(self, game, name, summary):
        fields = edit_game_details(self.database_path, game["id"], name, summary)
        game.update(fields)
        self.games.sort(key=lambda item: item["name"].casefold())
        self.recommendations = exclude_collection(self.recommendations, self.games)
        if self.details_window is not None and self.details_window.winfo_exists():
            if self.details_window.game_id == game["id"]:
                self.details_window.update_details()
        self.window.after_idle(self.refresh_library)

    def remove_game(self, game):
        delete_game(self.database_path, self.project_dir, game["id"])
        if game.get("favorite") and game["status"] == "beaten":
            self.recommendations = []
        self.games[:] = [record for record in self.games if record["id"] != game["id"]]
        self.details_window = None
        self.window.after_idle(self.refresh_library)

    def change_status(self, game, new_status):
        if game["status"] == "recommended" and new_status == "wishlist":
            self.add_recommended(game)
            return
        if new_status not in STATUS_LABELS:
            raise ValueError(f"Invalid status: {new_status}")
        if game["status"] == new_status:
            return
        update_game_status(self.database_path, game["id"], new_status)
        before_seeds = recommendation_seeds(self.games)
        game["status"] = new_status
        if before_seeds != recommendation_seeds(self.games):
            self.recommendations = []
        if self.details_window is not None and self.details_window.winfo_exists():
            if self.details_window.game_id == game["id"]:
                self.details_window.update_status(new_status, STATUS_BORDER_COLORS[new_status])
        self.window.after_idle(self.refresh_library)

    def accept_recommendations(self, suggestions):
        # The collection may have changed while the request was running.
        suggestions = exclude_collection(suggestions, self.games)
        save_recommendations(self.project_dir, suggestions, self.games)
        self.recommendations = suggestions
        self.refresh_library()
        return len(suggestions), len({game["platform"] for game in suggestions})

    def update_navigation(self):
        self.sidebar.update_selection(self.shelf_scope, self.games, self.recommendations)
        titles = {key: label for key, label, _ in SHELVES}
        self.library_title.configure(text=titles[self.shelf_scope])
        count = self.sidebar.counts[self.shelf_scope]
        self.library_subtitle.configure(text=f"{count} games · Your personal collection")

    def refresh_library(self):
        if self.overview_window is not None and self.overview_window.winfo_exists():
            self.overview_window.refresh()
        if hasattr(self.window, "_cover_tooltip"):
            self.window._cover_tooltip.hide()
        self.update_navigation()
        # Reconcile changed shelves and keep the remaining widgets.
        self.library_area._parent_canvas.yview_moveto(0)
        render_library(
            self.library_area, self.games, self.change_status, self.open_details,
            "" if self.exhibition else self.local_search.get_query(), self.recommendations,
            self.preferences, self.remember_section, self.exhibition, self.change_favorite, incremental=True, scope=self.shelf_scope,
        )

    def change_favorite(self, game, favorite):
        try:
            update_game_favorite(self.database_path, game["id"], favorite)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Favorites", f"Could not save favorite: {error}", parent=self.window)
            return
        game["favorite"] = favorite
        update_favorite_display(self.library_area, game)
        if game["status"] == "beaten" and self.recommendations:
            self.recommendations = []
            clear_recommended_display(self.library_area)
            self.update_navigation()
        if self.overview_window is not None and self.overview_window.winfo_exists():
            self.overview_window.refresh()
