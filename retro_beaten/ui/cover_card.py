"""Game covers, borders, and click actions."""

from PIL import Image
import customtkinter as ctk
from retro_beaten.ui.cover_cache import load_thumbnail
from tkinter import Menu

from retro_beaten.statuses import STATUS_LABELS, STATUS_BORDER_COLORS

COVER_SIZE = (150, 200)


def create_cover(parent, cover_path, size, status):
    """Create a cover with a border matching the game's status."""
    unavailable = False
    try:
        cover_image, display_size = load_thumbnail(cover_path, size)
    except (OSError, ValueError, Image.DecompressionBombError):
        unavailable = True
        display_size = size
        cover_image = Image.new("RGB", size, "#191B20")

    cover_display = ctk.CTkImage(
        light_image=cover_image,
        dark_image=cover_image,
        size=display_size
    )

    border_width = 3
    cover_frame = ctk.CTkFrame(
        master=parent,
        width=display_size[0] + 2 * border_width,
        height=display_size[1] + 2 * border_width,
        corner_radius=0,
        fg_color="transparent",
        border_width=border_width,
        border_color=STATUS_BORDER_COLORS[status]
    )

    cover_label = ctk.CTkLabel(
        master=cover_frame,
        image=cover_display,
        text="Cover unavailable" if unavailable else "",
        text_color="#969BA5",
        wraplength=max(60, display_size[0] - 12),
        width=display_size[0],
        height=display_size[1],
        padx=0,
        pady=0
    )
    # Padding keeps the border visible without covering the image.
    cover_label.pack(padx=border_width, pady=border_width)
    return cover_frame, cover_label


def attach_status_menu(cover_frame, cover_label, game, on_status_change):
    """Attach a status menu to a game cover."""
    menu = Menu(cover_frame, tearoff=False)

    def choose_status(new_status):
        on_status_change(game, new_status)

    options = {f"Mark as {label}": status for status, label in STATUS_LABELS.items()}
    if game["status"] == "recommended":
        options = {"Add to Wishlist": "wishlist"}

    for label, status in options.items():
        menu.add_command(
            label=label,
            command=lambda selected=status: choose_status(selected)
        )

    def show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            if menu.winfo_exists():
                menu.grab_release()

    cover_label.bind("<Button-3>", show_menu, add="+")
    cover_frame.bind("<Button-3>", show_menu, add="+")


def attach_details_click(cover_frame, cover_label, game, on_open_details):
    """Open details on a left click on either the image or its border."""
    def open_details(event):
        on_open_details(game)

    for widget in (cover_frame, cover_label):
        widget.configure(cursor="hand2")
        widget.bind("<Button-1>", open_details, add="+")


def resize_cover(frame, cover_path, size):
    """Resize an existing card without recreating its menu, bindings, or star."""
    unavailable = False
    try:
        image, display_size = load_thumbnail(cover_path, size)
    except (OSError, ValueError, Image.DecompressionBombError):
        unavailable = True
        display_size = size
        image = Image.new("RGB", size, "#191B20")
    display = ctk.CTkImage(light_image=image, dark_image=image, size=display_size)
    label = frame.winfo_children()[0]
    label.configure(image=display, width=display_size[0], height=display_size[1],
                    wraplength=max(60, display_size[0] - 12),
                    text="Cover unavailable" if unavailable else "")
    frame.configure(width=display_size[0] + 6, height=display_size[1] + 6)
