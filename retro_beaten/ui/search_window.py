"""Search, preview, and register games found on IGDB."""

from pathlib import Path
from queue import Empty, Queue
import sqlite3
from threading import Thread
from urllib.error import HTTPError, URLError

import customtkinter as ctk
from PIL import Image

from retro_beaten.services.igdb_api import load_credentials, get_access_token, search_games, download_cover
from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS, STATUS_CODES


def run_search(game_name, platform_id, results_queue):
    """Run network requests in the background and return results through the queue."""
    service = "Twitch"
    try:
        client_id, client_secret = load_credentials()
        token = get_access_token(client_id, client_secret)
        service = "IGDB"
        games = search_games(client_id, token, game_name, platform_id)
    except HTTPError as error:
        message = f"{service} returned HTTP error {error.code}."
        if error.code in (401, 403):
            message += " Check your credentials in .env."
        elif error.code == 429:
            message += " Wait a moment before trying again."
        results_queue.put(("error", message))
    except (URLError, TimeoutError):
        results_queue.put(("error", "Could not connect. Check your internet connection and try again."))
    except (ValueError, OSError):
        results_queue.put(("error", "Check your .env file. If it is configured, the service may have returned an invalid response."))
    except Exception:
        # Ensure the interface leaves its waiting state after unexpected failures.
        results_queue.put(("error", "An unexpected error occurred during the search."))
    else:
        results_queue.put(("success", games))


def run_preview(game, destination_dir, results_queue):
    """Download the preview without accessing interface components."""
    try:
        path = download_cover(game, destination_dir)
    except (URLError, TimeoutError, OSError, ValueError):
        results_queue.put(("error", "Could not download the cover. Select the result again to retry."))
    except Exception:
        results_queue.put(("error", "An unexpected error occurred while loading the cover."))
    else:
        results_queue.put(("preview", path))


class SearchWindow(ctk.CTkToplevel):
    """Manage search fields and state in a single window."""

    def __init__(self, parent, on_add_game, project_dir):
        super().__init__(parent, fg_color="#111827")
        self.title("Search games — Retro Beaten")
        self.geometry("820x720")
        self.minsize(720, 620)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.results_queue = Queue()
        self.poll_id = None
        self.busy = False
        self.on_add_game = on_add_game
        self.project_dir = Path(project_dir)
        self.games = []
        self.result_choices = {}
        self.selected_game = None
        self.preview_path = None
        self.cover_display = None
        self.already_added = False
        self.selected_platform_code = None
        self.platform_codes = {
            info["name"]: code for code, info in PLATFORMS.items()
        }

        ctk.CTkLabel(
            self, text="Search games", font=("Segoe UI", 24, "bold"),
            text_color="#E7B84B"
        ).pack(anchor="w", padx=24, pady=(20, 12))

        form = ctk.CTkFrame(self, fg_color="#1E293B")
        form.pack(fill="x", padx=24)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Platform", text_color="#F8FAFC").grid(
            row=0, column=0, padx=12, pady=12, sticky="w"
        )
        self.console_menu = ctk.CTkOptionMenu(
            form, values=list(self.platform_codes), fg_color="#374151",
            button_color="#374151", button_hover_color="#475569",
            text_color="#F8FAFC", command=lambda value: self.clear_results()
        )
        self.console_menu.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkLabel(form, text="Game name", text_color="#F8FAFC").grid(
            row=1, column=0, padx=12, pady=(0, 12), sticky="w"
        )
        self.name_entry = ctk.CTkEntry(
            form, placeholder_text="e.g. Tekken 3", fg_color="#111827",
            text_color="#F8FAFC", border_color="#374151"
        )
        self.name_entry.grid(row=1, column=1, padx=12, pady=(0, 12), sticky="ew")
        self.name_entry.bind("<Return>", lambda event: self.start_search())
        self.name_entry.bind("<KeyRelease>", self.on_name_changed)

        self.search_button = ctk.CTkButton(
            self, text="Search", command=self.start_search,
            fg_color="#E7B84B", hover_color="#C99B35", text_color="#111827"
        )
        self.search_button.pack(anchor="e", padx=24, pady=12)
        self.status_label = ctk.CTkLabel(
            self, text="Choose a platform and enter a game name.",
            text_color="#94A3B8", anchor="w", wraplength=560
        )
        self.status_label.pack(fill="x", padx=24, pady=(0, 8))

        self.result_menu = ctk.CTkOptionMenu(
            self, values=["Select um resultado"], state="disabled",
            command=self.select_result, fg_color="#374151",
            button_color="#374151", button_hover_color="#475569"
        )
        self.result_menu.pack(fill="x", padx=24, pady=(0, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(12, 20))
        ctk.CTkLabel(footer, text="Status", text_color="#F8FAFC").pack(side="left", padx=(0, 12))
        self.game_status_menu = ctk.CTkOptionMenu(
            footer, values=list(STATUS_LABELS.values()),
            fg_color="#374151", button_color="#374151", button_hover_color="#475569"
        )
        self.game_status_menu.pack(side="left")
        self.add_button = ctk.CTkButton(
            footer, text="Add to collection", command=self.add_selected_game,
            state="disabled", fg_color="#E7B84B", hover_color="#C99B35",
            text_color="#111827"
        )
        self.add_button.pack(side="right")

        details = ctk.CTkFrame(self, fg_color="#1E293B")
        details.pack(fill="both", expand=True, padx=24)
        details.grid_columnconfigure(1, weight=1)
        details.grid_rowconfigure(0, weight=1)
        self.preview_panel = details
        self.cover_label = None
        self.reset_cover("Select a game")
        self.results_box = ctk.CTkTextbox(
            details, fg_color="#1E293B", text_color="#F8FAFC",
            font=("Segoe UI", 14), wrap="word", state="disabled"
        )
        self.results_box.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self.set_results_text("Search for a game and select a result to preview its cover and description.")

    def reset_cover(self, text):
        # Recreate the label to clear Tkinter's internal image as well.
        if self.cover_label is not None:
            self.cover_label.destroy()
        self.cover_display = None
        self.cover_label = ctk.CTkLabel(
            self.preview_panel, text=text, width=150, height=200,
            text_color="#94A3B8", wraplength=145
        )
        self.cover_label.grid(row=0, column=0, sticky="n", padx=16, pady=16)

    def on_name_changed(self, event):
        if event.keysym != "Return" and not self.busy and self.games:
            self.clear_results()

    def clear_results(self):
        self.games = []
        self.result_choices = {}
        self.selected_game = None
        self.preview_path = None
        self.already_added = False
        self.reset_cover("Select a game")
        self.result_menu.configure(values=["Select um resultado"], state="disabled")
        self.result_menu.set("Select um resultado")
        self.add_button.configure(state="disabled")
        self.set_results_text("")
        self.status_label.configure(text="Choose a platform and enter a game name.")

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.search_button.configure(state=state)
        self.console_menu.configure(state=state)
        self.name_entry.configure(state=state)
        self.game_status_menu.configure(state=state)
        self.result_menu.configure(state="normal" if self.games and not busy else "disabled")
        can_add = self.preview_path is not None and self.selected_game is not None and not self.already_added
        self.add_button.configure(state="normal" if can_add and not busy else "disabled")

    def select_result(self, choice):
        if self.busy:
            return
        self.selected_game = self.result_choices[choice]
        self.preview_path = None
        self.already_added = False
        game = self.selected_game
        console_name = PLATFORMS[self.selected_platform_code]["name"]
        platforms = ", ".join(p["name"] for p in (game.get("platforms") or []))
        self.set_results_text(
            f"{game.get('name', 'Name unavailable')}\n\n"
            f"Selected platform: {console_name}\n"
            f"Available platforms: {platforms or 'Not provided'}\n\n"
            f"{game.get('summary') or 'Description unavailable.'}\n\nSource: IGDB"
        )
        self.reset_cover("Loading cover...")
        if not (game.get("cover") or {}).get("image_id"):
            self.cover_label.configure(text="Cover unavailable")
            self.status_label.configure(text="This game has no cover on IGDB. Use Add manually to choose a local image.")
            self.set_busy(False)
            return

        self.status_label.configure(text="Loading cover preview...")
        self.set_busy(True)
        Thread(
            target=run_preview,
            args=(game, self.project_dir / "assets" / "previews", self.results_queue),
            daemon=True
        ).start()
        self.poll_id = self.after(100, self.check_results)

    def show_preview(self, path):
        try:
            with Image.open(path) as image:
                cover = image.copy()
            scale = min(150 / cover.width, 200 / cover.height)
            display_size = (max(1, round(cover.width * scale)), max(1, round(cover.height * scale)))
            self.cover_display = ctk.CTkImage(light_image=cover, dark_image=cover, size=display_size)
            self.cover_label.configure(image=self.cover_display, text="")
        except (OSError, ValueError):
            self.status_label.configure(text="Could not open the cover. Select the result again.")
            self.cover_label.configure(text="Cover unavailable")
            return
        self.preview_path = path
        self.status_label.configure(text="Check the game and platform, choose a status, and add it to your collection.")
        self.set_busy(False)

    def add_selected_game(self):
        if self.busy or self.selected_game is None or self.preview_path is None or self.already_added:
            return
        self.set_busy(True)
        try:
            # The callback saves locally and refreshes the main shelf.
            self.on_add_game(
                self.selected_game, self.selected_platform_code,
                STATUS_CODES[self.game_status_menu.get()], self.preview_path
            )
        except ValueError as error:
            self.status_label.configure(text=str(error))
        except (OSError, sqlite3.Error):
            self.status_label.configure(text="Could not save the game. Check access to the collection folder and try again.")
        else:
            self.already_added = True
            self.status_label.configure(text=f"{self.selected_game['name']} was added to your collection!")
        finally:
            self.set_busy(False)

    def set_results_text(self, text):
        self.results_box.configure(state="normal")
        self.results_box.delete("1.0", "end")
        self.results_box.insert("1.0", text)
        self.results_box.configure(state="disabled")

    def start_search(self):
        if self.busy:
            return
        game_name = self.name_entry.get().strip()
        if not game_name:
            self.status_label.configure(text="Enter a game name to search.")
            self.name_entry.focus_set()
            return

        self.clear_results()
        self.selected_platform_code = self.platform_codes[self.console_menu.get()]
        platform_id = PLATFORMS[self.selected_platform_code]["igdb_id"]
        self.set_busy(True)
        self.search_button.configure(text="Searching...")
        self.status_label.configure(text="Searching IGDB...")
        self.set_results_text("")

        # The worker uses only data and network operations, never Tkinter widgets.
        Thread(
            target=run_search,
            args=(game_name, platform_id, self.results_queue),
            daemon=True
        ).start()
        self.poll_id = self.after(100, self.check_results)

    def check_results(self):
        self.poll_id = None
        try:
            status, result = self.results_queue.get_nowait()
        except Empty:
            self.poll_id = self.after(100, self.check_results)
            return

        self.set_busy(False)
        self.search_button.configure(text="Search")
        if status == "error":
            self.status_label.configure(text=result)
            if self.selected_game is not None:
                self.cover_label.configure(text="Cover unavailable")
            return
        if status == "preview":
            self.show_preview(result)
            return

        self.games = result
        console_name = PLATFORMS[self.selected_platform_code]["name"]
        if not result:
            self.status_label.configure(text=f"No results for {console_name}. Try a shorter name.")
            return

        self.status_label.configure(text=f"Results for {console_name} — data from IGDB")
        self.result_choices = {
            f"{index}. {game.get('name', 'Name unavailable')}": game
            for index, game in enumerate(result, start=1)
        }
        self.result_menu.configure(values=list(self.result_choices), state="normal")
        self.result_menu.set("Select um resultado")
        self.set_results_text("Select a result above to preview its cover and description.")

    def destroy(self):
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
