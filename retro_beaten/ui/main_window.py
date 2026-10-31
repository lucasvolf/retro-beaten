"""Main window and application header."""

import customtkinter as ctk


def create_window():
    """Create and configure the main window."""
    window = ctk.CTk()
    window.title("Retro Beaten")
    window.geometry("1000x650")
    window.configure(fg_color="#111827")
    # Maximize after CustomTkinter finishes opening the window.
    window.after(0, window.state, "zoomed")
    return window


def create_header(parent, on_search, on_manual, on_backup=None):
    """Build the title and slogan panel."""
    header_frame = ctk.CTkFrame(
        master=parent,
        fg_color="#1E293B"
    )
    header_frame.pack(fill="x", padx=20, pady=20)

    title_label = ctk.CTkLabel(
        master=header_frame,
        text="RETRO BEATEN",
        font=("Segoe UI", 30, "bold"),
        text_color="#E7B84B"
    )
    title_label.pack(pady=(30, 0))

    slogan_label = ctk.CTkLabel(
        master=header_frame,
        text="A Collection of Adventures, Not Achievements.",
        font=("Segoe UI", 14),
        text_color="#94A3B8"
    )
    slogan_label.pack(pady=(4, 24))

    actions = ctk.CTkFrame(header_frame, fg_color="transparent")
    actions.pack(pady=(0, 20))
    search_button = ctk.CTkButton(
        actions, text="Search IGDB", command=on_search,
        fg_color="#E7B84B", hover_color="#C99B35", text_color="#111827"
    )
    search_button.pack(side="left", padx=(0, 12))
    ctk.CTkButton(
        actions, text="Add manually", command=on_manual,
        fg_color="#374151", hover_color="#475569", text_color="#F8FAFC"
    ).pack(side="left")
    if on_backup is not None:
        ctk.CTkButton(
            actions, text="Backup and restore", command=on_backup,
            fg_color="#374151", hover_color="#475569", text_color="#F8FAFC",
        ).pack(side="left", padx=(12, 0))

    return header_frame
