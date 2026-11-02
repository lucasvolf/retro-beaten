"""Game details using only local data and covers."""

import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel
import sqlite3
from tkinter import messagebox
from PIL import Image

from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS
from retro_beaten.ui.cover_window import CoverWindow
from retro_beaten.ui.edit_game_window import EditGameWindow


class DetailsWindow(ManagedToplevel):
    """Display a collection record without making network requests."""

    def __init__(self, parent, game, status_color, on_wishlist=None, on_cover_change=None, on_delete=None, on_edit=None):
        super().__init__(parent, fg_color="#101114")
        self.game_id = game["id"]
        self.game = game
        self.on_cover_change = on_cover_change
        self.on_delete = on_delete
        self.cover_window = None
        self.edit_window = None
        self.on_edit = on_edit
        self.title(f"{game['name']} — Retro Beaten")
        self.geometry("920x650")
        self.minsize(860, 580)
        self.transient(parent)
        self.bind("<Escape>", lambda event: self.destroy())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text="RETRO BEATEN  /  YOUR ADVENTURES", font=("Segoe UI", 12, "bold"),
                     text_color="#969BA5", anchor="w").grid(row=0, column=0, sticky="ew", padx=28, pady=(22, 12))
        content = ctk.CTkFrame(self, fg_color="#191B20", border_width=1, border_color="#2D3037")
        content.grid(row=1, column=0, sticky="nsew", padx=24)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)
        art = ctk.CTkFrame(content, fg_color="#15171B", border_width=1, border_color=status_color)
        self.art = art
        art.grid(row=0, column=0, sticky="n", padx=20, pady=22)
        self.cover_display = None
        self.cover_label = ctk.CTkLabel(art, text="Cover unavailable", width=240, height=320,
                                       text_color="#969BA5")
        self.cover_label.pack(padx=10, pady=10)
        self.show_cover(game["cover_path"])
        info = ctk.CTkFrame(content, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew", padx=(0, 22), pady=22)
        info.grid_columnconfigure(0, weight=1)
        info.grid_rowconfigure(4, weight=1)
        self.name_label = ctk.CTkLabel(info, text=game["name"], font=("Segoe UI", 27, "bold"),
                                      text_color="#F1F2F4", wraplength=470, justify="left", anchor="w")
        self.name_label.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        info.bind("<Configure>", lambda event: self.name_label.configure(wraplength=max(200, event.width)), add="+")
        metadata = ctk.CTkFrame(info, fg_color="transparent")
        metadata.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        platform_name = PLATFORMS.get(game["platform"], {}).get("name", game["platform"])
        self.platform_label = ctk.CTkLabel(metadata, text=f"Platform: {platform_name}",
                                          font=("Segoe UI", 13), text_color="#969BA5")
        self.platform_label.pack(side="left")
        self.status_label = ctk.CTkLabel(metadata, text="", font=("Segoe UI", 12, "bold"),
                                        fg_color="#15171B", corner_radius=6, padx=12)
        self.status_label.pack(side="right", padx=(10, 0))
        self.update_status(game["status"], status_color)
        if game.get("reason"):
            ctk.CTkLabel(info, text=game["reason"], text_color="#E7B84B", wraplength=430,
                         justify="left", anchor="w").grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(info, text="ABOUT THIS ADVENTURE", font=("Segoe UI", 11, "bold"),
                     text_color="#969BA5", anchor="w").grid(row=3, column=0, sticky="ew", pady=(4, 8))
        self.description_box = ctk.CTkTextbox(info, fg_color="transparent", text_color="#CBD5E1",
                                             font=("Segoe UI", 14), wrap="word", border_width=0)
        self.description_box.grid(row=4, column=0, sticky="nsew")
        self.update_details()
        if game.get("igdb_id"):
            ctk.CTkLabel(info, text="IGDB  /  Available offline", text_color="#969BA5", font=("Segoe UI", 11),
                         anchor="w").grid(row=5, column=0, sticky="ew", pady=(12, 0))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=20)
        if on_wishlist is not None:
            self.wishlist_button = ctk.CTkButton(footer, text="Add to Wishlist", command=lambda: on_wishlist(game),
                                                fg_color="#E7B84B", hover_color="#F4CE73", text_color="#101114")
            self.wishlist_button.pack(side="left", padx=(0, 10))
        if on_edit is not None:
            self.edit_button = ctk.CTkButton(footer, text="Edit game", command=self.open_edit_window, width=110)
            self.edit_button.pack(side="left", padx=(0, 10))
        if on_cover_change is not None:
            self.change_cover_button = ctk.CTkButton(footer, text="Change cover", command=self.open_cover_window, width=110)
            self.change_cover_button.pack(side="left", padx=(0, 10))
        if on_delete is not None:
            self.delete_button = ctk.CTkButton(footer, text="Delete game", command=self.confirm_delete, width=110,
                                              fg_color="transparent", border_color="#7F3847", text_color="#FCA5A5", hover_color="#442535")
            self.delete_button.pack(side="left")
        ctk.CTkButton(footer, text="Close", command=self.destroy, width=90).pack(side="right")

    def update_status(self, status, color):
        if hasattr(self, "art"):
            self.art.configure(border_color=color)
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
            self.cover_label.configure(image=None, text="Cover unavailable")
            self.cover_display = None

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
