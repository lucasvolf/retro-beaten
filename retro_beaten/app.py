"""Coordinate the collection, windows, and interface actions."""

from pathlib import Path
import sqlite3
from tkinter import messagebox

from retro_beaten.paths import get_data_dir
from retro_beaten.statuses import STATUS_LABELS, STATUS_BORDER_COLORS
from retro_beaten.services.collection import (
    register_game, register_manual_game, replace_cover, delete_game, edit_game_details,
)
from retro_beaten.services.recommendations import (
    load_recommendations, save_recommendations, exclude_collection,
)
from retro_beaten.storage.database import initialize_database, load_saved_games, update_game_status
from retro_beaten.ui.main_window import create_window, create_header
from retro_beaten.ui.library_view import create_library_area, render_library
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

        self.window = create_window()
        self.search_window = None
        self.details_window = None
        self.manual_window = None
        self.backup_window = None
        self.build_interface()
        self.refresh_library()

    def build_interface(self):
        """Connect each visual component to application actions."""
        create_header(self.window, self.open_search, self.open_manual, self.open_backup)
        self.local_search = LibrarySearch(self.window, self.refresh_library)
        self.local_search.pack(fill="x", padx=40, pady=(0, 16))
        self.recommendation_controls = RecommendationControls(
            self.window, self.project_dir, lambda: self.games, lambda: self.recommendations,
            self.accept_recommendations,
        )
        self.recommendation_controls.pack(fill="x", padx=40, pady=(0, 12))
        self.library_area = create_library_area(self.window)

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
        game["status"] = new_status
        if self.details_window is not None and self.details_window.winfo_exists():
            if self.details_window.game_id == game["id"]:
                self.details_window.update_status(new_status, STATUS_BORDER_COLORS[new_status])
        self.window.after_idle(self.refresh_library)

    def accept_recommendations(self, suggestions):
        # The collection may have changed while the request was running.
        suggestions = exclude_collection(suggestions, self.games)
        save_recommendations(self.project_dir, suggestions)
        self.recommendations = suggestions
        self.refresh_library()
        return len(suggestions), len({game["platform"] for game in suggestions})

    def refresh_library(self):
        # The new list may be shorter: rebuild sections from the visible area.
        self.library_area._parent_canvas.yview_moveto(0)
        for section in self.library_area.winfo_children():
            section.destroy()
        render_library(
            self.library_area, self.games, self.change_status, self.open_details,
            self.local_search.get_query(), self.recommendations,
        )
