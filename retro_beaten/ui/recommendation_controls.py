"""Refresh button and background query communication."""

from queue import Empty, Queue
from threading import Thread
from urllib.error import HTTPError, URLError

import customtkinter as ctk

from retro_beaten.services.recommendations import fetch_recommendations


def run_recommendations(collection, previous_ids, project_dir, queue):
    try:
        games = fetch_recommendations(
            collection, previous_ids, project_dir,
            progress=lambda text: queue.put(("progress", text))
        )
    except HTTPError as error:
        queue.put(("error", f"The service returned HTTP error {error.code}. Please try again later."))
    except (URLError, TimeoutError):
        queue.put(("error", "Could not connect to IGDB. Previous recommendations are still available."))
    except ValueError as error:
        queue.put(("error", str(error)))
    except Exception:
        queue.put(("error", "Could not refresh. Previous recommendations were kept."))
    else:
        queue.put(("success", games))


class RecommendationControls(ctk.CTkFrame):
    def __init__(self, parent, project_dir, get_collection, get_recommendations, on_ready):
        super().__init__(parent, fg_color="transparent")
        self.project_dir = project_dir
        self.get_collection = get_collection
        self.get_recommendations = get_recommendations
        self.on_ready = on_ready
        self.queue = Queue()
        self.poll_id = None
        self.busy = False
        self.button = ctk.CTkButton(
            self, text="Refresh recommendations", command=self.start_refresh,
            fg_color="#374151", hover_color="#475569", text_color="#F8FAFC",
        )
        self.button.pack(side="left", padx=(0, 16))
        self.message = ctk.CTkLabel(
            self, text="Recommendations based on your Beaten games, across platforms.",
            text_color="#94A3B8", anchor="w", wraplength=580,
        )
        self.message.pack(side="left", fill="x", expand=True)

    def start_refresh(self):
        if self.busy:
            return
        self.busy = True
        self.button.configure(state="disabled")
        self.message.configure(text="Preparing recommendations...")
        collection = [dict(game) for game in self.get_collection()]
        previous_ids = [game["igdb_id"] for game in self.get_recommendations()]
        Thread(target=run_recommendations,
               args=(collection, previous_ids, self.project_dir, self.queue), daemon=True).start()
        self.poll_id = self.after(100, self.check_results)

    def check_results(self):
        self.poll_id = None
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == "progress":
                    self.message.configure(text=value)
                    continue
                if kind == "success":
                    try:
                        count, platforms = self.on_ready(value)
                        text = f"{count} recommendations across {platforms} platforms. Click a cover to explore."
                    except Exception:
                        text = "Could not save recommendations. Please try again."
                else:
                    text = value
                self.message.configure(text=text)
                self.busy = False
                self.button.configure(state="normal")
        except Empty:
            pass
        if self.busy:
            self.poll_id = self.after(100, self.check_results)

    def destroy(self):
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
