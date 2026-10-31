"""Game details using only local data and covers."""

import customtkinter as ctk
import sqlite3
from tkinter import messagebox
from PIL import Image

from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS
from retro_beaten.ui.cover_window import CoverWindow
from retro_beaten.ui.edit_game_window import EditGameWindow


class DetailsWindow(ctk.CTkToplevel):
    """Display a collection record without making network requests."""

    def __init__(self, parent, game, status_color, on_wishlist=None, on_cover_change=None, on_delete=None, on_edit=None):
        super().__init__(parent, fg_color="#111827")
        self.game_id = game["id"]
        self.game = game
        self.on_cover_change = on_cover_change
        self.on_delete = on_delete
        self.cover_window = None
        self.edit_window = None
        self.on_edit = on_edit
        self.title(f"{game['name']} — Retro Beaten")
        self.geometry("850x600")
        self.minsize(720, 520)
        self.transient(parent)
        self.bind("<Escape>", lambda event: self.destroy())

        self.name_label = ctk.CTkLabel(
            self, text=game["name"], font=("Segoe UI", 24, "bold"),
            text_color="#E7B84B", wraplength=640, justify="left", anchor="w"
        )
        self.name_label.pack(fill="x", padx=24, pady=(24, 8))

        metadata = ctk.CTkFrame(self, fg_color="transparent")
        metadata.pack(fill="x", padx=24, pady=(0, 16))
        platform_name = PLATFORMS.get(game["platform"], {}).get("name", game["platform"])
        self.platform_label = ctk.CTkLabel(
            metadata, text=f"Platform: {platform_name}",
            font=("Segoe UI", 15), text_color="#F8FAFC"
        )
        self.platform_label.pack(side="left")
        self.status_label = ctk.CTkLabel(
            metadata, text="", font=("Segoe UI", 15, "bold")
        )
        self.status_label.pack(side="right")
        self.update_status(game["status"], status_color)

        if game.get("reason"):
            ctk.CTkLabel(
                self, text=game["reason"], text_color="#94A3B8", wraplength=720,
                justify="left", anchor="w",
            ).pack(fill="x", padx=24, pady=(0, 12))

        if on_wishlist is not None:
            self.wishlist_button = ctk.CTkButton(
                self, text="Add to Wishlist", command=lambda: on_wishlist(game),
                fg_color="#22C55E", hover_color="#16A34A", text_color="#111827",
            )
            self.wishlist_button.pack(side="bottom", anchor="e", padx=24, pady=(0, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=20)
        if on_edit is not None:
            self.edit_button = ctk.CTkButton(
                footer, text="Edit game", command=self.open_edit_window,
                fg_color="#374151", hover_color="#475569",
            )
            self.edit_button.pack(side="left", padx=(0, 12))
        if on_cover_change is not None:
            self.change_cover_button = ctk.CTkButton(
                footer, text="Change cover", command=self.open_cover_window,
                fg_color="#374151", hover_color="#475569",
            )
            self.change_cover_button.pack(side="left", padx=(0, 12))
        if on_delete is not None:
            self.delete_button = ctk.CTkButton(
                footer, text="Delete game", command=self.confirm_delete,
                fg_color="#B91C1C", hover_color="#991B1B",
            )
            self.delete_button.pack(side="left")
        ctk.CTkButton(
            footer, text="Close", command=self.destroy,
            fg_color="#374151", hover_color="#475569", text_color="#F8FAFC"
        ).pack(side="right")

        content = ctk.CTkFrame(self, fg_color="#1E293B")
        content.pack(fill="both", expand=True, padx=24)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(1, weight=1)

        self.cover_display = None
        self.cover_label = ctk.CTkLabel(
            content, text="Cover unavailable", width=240, height=320,
            text_color="#94A3B8"
        )
        self.cover_label.grid(row=0, column=0, rowspan=2, sticky="n", padx=16, pady=16)
        self.show_cover(game["cover_path"])

        ctk.CTkLabel(
            content, text="Description", font=("Segoe UI", 17, "bold"),
            text_color="#F8FAFC", anchor="w"
        ).grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(16, 4))
        self.description_box = ctk.CTkTextbox(
            content, fg_color="transparent", text_color="#F8FAFC",
            font=("Segoe UI", 15), wrap="word"
        )
        self.description_box.grid(row=1, column=1, sticky="nsew", padx=(0, 16), pady=(0, 16))
        self.update_details()
        if game.get("igdb_id"):
            ctk.CTkLabel(
                content, text="Added via IGDB • Available offline",
                text_color="#94A3B8", anchor="w"
            ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))

    def update_status(self, status, color):
        self.status_label.configure(text=STATUS_LABELS.get(status, status.capitalize()), text_color=color)

    def update_details(self):
        self.title(f"{self.game['name']} — Retro Beaten")
        self.name_label.configure(text=self.game["name"])
        self.description_box.configure(state="normal")
        self.description_box.delete("1.0", "end")
        summary = (self.game.get("summary") or "").strip()
        self.description_box.insert("1.0", summary or "This game does not have a saved description yet.")
        self.description_box.configure(state="disabled")

    def open_edit_window(self):
        if self.edit_window is not None and self.edit_window.winfo_exists():
            self.edit_window.deiconify()
            self.edit_window.lift()
            self.edit_window.focus_set()
            return
        self.edit_window = EditGameWindow(self, self.game, self.on_edit)

    def show_cover(self, path):
        try:
            with Image.open(path) as source:
                cover = source.copy()
            scale = min(240 / cover.width, 320 / cover.height)
            size = (max(1, round(cover.width * scale)), max(1, round(cover.height * scale)))
            display = ctk.CTkImage(light_image=cover, dark_image=cover, size=size)
            self.cover_label.configure(image=display, text="")
            self.cover_display = display
        except (OSError, ValueError, Image.DecompressionBombError):
            # The description remains available even if the local cover is missing.
            pass

    def open_cover_window(self):
        if self.cover_window is not None and self.cover_window.winfo_exists():
            self.cover_window.lift()
            self.cover_window.focus_set()
            return
        self.cover_window = CoverWindow(self, self.game, self.on_cover_change)

    def confirm_delete(self):
        platform = PLATFORMS[self.game["platform"]]["name"]
        confirmed = messagebox.askyesno(
            "Delete game",
            f"Delete {self.game['name']} ({platform}) from your collection?\n\n"
            "The game and its app-managed cover copy will be removed.\n"
            "The original image on your computer will be kept.",
            parent=self, icon="warning", default="no",
        )
        if not confirmed:
            return
        try:
            self.on_delete(self.game)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Could not delete game", str(error), parent=self)
            return
        self.destroy()
