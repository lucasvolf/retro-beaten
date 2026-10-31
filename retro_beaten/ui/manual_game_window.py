"""Local game registration form, independent of IGDB."""

from pathlib import Path
import sqlite3
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS, STATUS_CODES


class ManualGameWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_add_game):
        super().__init__(parent, fg_color="#111827")
        self.title("Add manually — Retro Beaten")
        self.geometry("760x650")
        self.minsize(700, 600)
        self.transient(parent)
        self.on_add_game = on_add_game
        self.cover_path = None
        self.cover_display = None
        self.platform_codes = {info["name"]: code for code, info in PLATFORMS.items()}

        ctk.CTkLabel(
            self, text="Add manually", font=("Segoe UI", 24, "bold"),
            text_color="#E7B84B"
        ).pack(anchor="w", padx=24, pady=(20, 16))

        form = ctk.CTkFrame(self, fg_color="#1E293B")
        form.pack(fill="both", expand=True, padx=24)
        form.grid_columnconfigure(1, weight=1)
        form.grid_rowconfigure(3, weight=1)
        self.name_entry = ctk.CTkEntry(form, placeholder_text="e.g. To the Moon")
        self.platform_menu = ctk.CTkOptionMenu(form, values=list(self.platform_codes))
        self.platform_menu.set("PC")
        self.status_menu = ctk.CTkOptionMenu(form, values=list(STATUS_LABELS.values()))
        for row, (label, widget) in enumerate((
            ("Game name", self.name_entry), ("Platform", self.platform_menu), ("Status", self.status_menu)
        )):
            ctk.CTkLabel(form, text=label, text_color="#F8FAFC").grid(
                row=row, column=0, sticky="w", padx=16, pady=(16, 0)
            )
            widget.grid(row=row, column=1, sticky="ew", padx=16, pady=(16, 0))

        ctk.CTkLabel(form, text="Description\n(optional)", text_color="#F8FAFC", justify="left").grid(
            row=3, column=0, sticky="nw", padx=16, pady=16
        )
        self.summary_box = ctk.CTkTextbox(form, height=90, wrap="word")
        self.summary_box.grid(row=3, column=1, sticky="nsew", padx=16, pady=16)

        cover_panel = ctk.CTkFrame(form, fg_color="transparent")
        cover_panel.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))
        self.cover_label = ctk.CTkLabel(cover_panel, text="No cover", width=105, height=140, text_color="#94A3B8")
        self.cover_label.pack(side="left", padx=(0, 20))
        self.choose_button = ctk.CTkButton(
            cover_panel, text="Choose cover...", command=self.choose_cover,
            fg_color="#374151", hover_color="#475569"
        )
        self.choose_button.pack(anchor="w", pady=(12, 8))
        self.filename_label = ctk.CTkLabel(
            cover_panel, text="PNG, JPEG or WebP", text_color="#94A3B8", wraplength=360, justify="left"
        )
        self.filename_label.pack(anchor="w")

        self.message_label = ctk.CTkLabel(self, text="", text_color="#94A3B8", wraplength=640)
        self.message_label.pack(fill="x", padx=24, pady=8)
        self.add_button = ctk.CTkButton(
            self, text="Add to collection", command=self.save_game,
            fg_color="#E7B84B", hover_color="#C99B35", text_color="#111827"
        )
        self.add_button.pack(anchor="e", padx=24, pady=(0, 20))

    def choose_cover(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Choose cover",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]
        )
        if filename:
            self.load_cover(Path(filename))

    def load_cover(self, path):
        try:
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported format")
                cover = image.copy()
            scale = min(105 / cover.width, 140 / cover.height)
            size = (max(1, round(cover.width * scale)), max(1, round(cover.height * scale)))
            display = ctk.CTkImage(light_image=cover, dark_image=cover, size=size)
            # Keep the previous image alive until the label receives the new one.
            self.cover_label.configure(image=display, text="")
        except (OSError, ValueError, Image.DecompressionBombError):
            self.message_label.configure(text="Could not open this image. Choose a valid PNG, JPEG or WebP cover.")
            return
        self.cover_display = display
        self.cover_path = Path(path)
        self.filename_label.configure(text=self.cover_path.name)
        self.message_label.configure(text="The cover will be copied to your collection when you save.")

    def save_game(self):
        name = self.name_entry.get().strip()
        if not name:
            self.message_label.configure(text="Enter a game name.")
            self.name_entry.focus_set()
            return
        if self.cover_path is None:
            self.message_label.configure(text="Choose a cover image.")
            return
        self.add_button.configure(state="disabled")
        try:
            self.on_add_game(
                name, self.platform_codes[self.platform_menu.get()],
                STATUS_CODES[self.status_menu.get()], self.cover_path,
                self.summary_box.get("1.0", "end").strip()
            )
        except ValueError as error:
            self.message_label.configure(text=str(error))
        except (OSError, sqlite3.Error):
            self.message_label.configure(text="Could not save. Check the image and access to the collection folder.")
        else:
            self.destroy()
            return
        self.add_button.configure(state="normal")
