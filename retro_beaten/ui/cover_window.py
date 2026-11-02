"""Local cover selection with preview and explicit saving."""

from io import BytesIO
from pathlib import Path
import sqlite3
from tkinter import filedialog

import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel
from PIL import Image


class CoverWindow(ManagedToplevel):
    def __init__(self, parent, game, on_save):
        super().__init__(parent, fg_color="#101114")
        self.title("Change cover — Retro Beaten")
        self.geometry("520x620")
        self.minsize(480, 600)
        self.transient(parent)
        self.bind("<Escape>", lambda event: self.destroy())
        self.game = game
        self.on_save = on_save
        self.image_data = None
        self.cover_display = None

        ctk.CTkLabel(self, text=f"Change cover for {game['name']}",
                     font=("Segoe UI", 20, "bold"), text_color="#E7B84B",
                     wraplength=450).pack(padx=24, pady=(20, 12))
        self.preview = ctk.CTkLabel(self, text="Choose an image", width=240, height=320,
                                    text_color="#969BA5", fg_color="#191B20")
        self.preview.pack(padx=24, pady=(0, 12))
        ctk.CTkButton(self, text="Choose image...", command=self.choose_image,
                      fg_color="#24272D", hover_color="#33373F").pack()
        self.message = ctk.CTkLabel(self, text="PNG, JPEG or WebP. Check the preview before saving.",
                                    text_color="#969BA5", wraplength=450)
        self.message.pack(fill="x", padx=24, pady=12)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=20)
        self.cancel_button = ctk.CTkButton(footer, text="Cancel", command=self.destroy,
                                           fg_color="#24272D", hover_color="#33373F")
        self.cancel_button.pack(side="left")
        self.save_button = ctk.CTkButton(footer, text="Save cover", command=self.save_cover,
                                         state="disabled", fg_color="#E7B84B",
                                         hover_color="#C99B35", text_color="#101114")
        self.save_button.pack(side="right")

    def choose_image(self):
        filename = filedialog.askopenfilename(
            parent=self, title="Choose a new cover",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
        )
        if filename:
            self.load_preview(Path(filename))

    def load_preview(self, path):
        try:
            image_data = Path(path).read_bytes()
            with Image.open(BytesIO(image_data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Unsupported format")
                cover = source.copy()
            scale = min(240 / cover.width, 320 / cover.height)
            size = (max(1, round(cover.width * scale)), max(1, round(cover.height * scale)))
            display = ctk.CTkImage(light_image=cover, dark_image=cover, size=size)
            # Keep the previous reference until Tk receives the new image.
            self.preview.configure(image=display, text="")
        except (OSError, ValueError, Image.DecompressionBombError):
            # Disable saving to avoid accidentally confirming a previous preview.
            self.image_data = None
            self.save_button.configure(state="disabled")
            self.message.configure(text="Could not open this image. Choose a valid PNG, JPEG or WebP file.")
            return
        self.cover_display = display
        self.image_data = image_data
        self.save_button.configure(state="normal")
        self.message.configure(text=f"Preview: {Path(path).name}\nClick Save cover to confirm.")

    def save_cover(self):
        if self.image_data is None:
            return
        self.save_button.configure(state="disabled")
        try:
            self.on_save(self.game, self.image_data)
        except ValueError as error:
            self.message.configure(text=str(error))
        except (OSError, sqlite3.Error, Image.DecompressionBombError):
            self.message.configure(text="Could not save. Your current cover was kept; please try again.")
        else:
            self.destroy()
            return
        self.save_button.configure(state="normal")
