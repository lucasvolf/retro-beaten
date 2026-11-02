"""Small independent favorite control, without opening game details."""

import customtkinter as ctk


def add_favorite_star(frame, game, on_change, exhibition=False):
    if game["status"] == "recommended":
        return

    def toggle():
        if on_change is not None:
            on_change(game, not bool(game.get("favorite")))
            paint()

    star = ctk.CTkButton(frame, text="★", width=28, height=28,
                         font=("Segoe UI Symbol", 21), corner_radius=6,
                         fg_color="#15171B", hover_color="#30343C", border_width=0,
                         command=toggle, state="disabled" if exhibition else "normal")

    last_color = None

    def paint():
        nonlocal last_color
        color = "#E7B84B" if game.get("favorite") else "#64748B"
        if color != last_color:
            star.configure(text_color=color, text_color_disabled=color)
            last_color = color

    paint()
    star.place(relx=1, rely=1, x=-6, y=-6, anchor="se")
    frame.favorite_star = star
    frame.repaint_favorite = paint
