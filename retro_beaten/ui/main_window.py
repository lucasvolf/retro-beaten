"""Main desktop window factory."""

import customtkinter as ctk
from retro_beaten.ui.theme import apply_theme


def create_window():
    apply_theme()
    window = ctk.CTk()
    window.title("Retro Beaten")
    window.geometry("1000x650")
    window.minsize(980, 620)
    window.configure(fg_color="#101114")
    window.after(0, window.state, "zoomed")
    return window
