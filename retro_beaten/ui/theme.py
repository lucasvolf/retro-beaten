"""Shared dark collector palette and widget defaults."""

import customtkinter as ctk

BACKGROUND = "#101114"
PANEL = "#191B20"
BORDER = "#2D3037"
GOLD = "#E7B84B"
TEXT = "#F1F2F4"
MUTED = "#969BA5"


def apply_theme():
    ctk.set_appearance_mode("dark")
    theme = ctk.ThemeManager.theme
    theme["CTkButton"].update(fg_color="#24272D", hover_color="#33373F",
                             text_color=TEXT, corner_radius=7, border_width=1, border_color=BORDER)
    theme["CTkOptionMenu"].update(fg_color="#22252B", button_color="#30343C",
                                 button_hover_color="#454A55", text_color=TEXT,
                                 dropdown_fg_color=PANEL, dropdown_hover_color="#30343C",
                                 dropdown_text_color=TEXT, corner_radius=7)
    theme["CTkEntry"].update(fg_color="#15171B", border_color=BORDER, text_color=TEXT,
                            placeholder_text_color=MUTED, corner_radius=7)
    theme["CTkTextbox"].update(fg_color="#15171B", border_color=BORDER, text_color=TEXT,
                              scrollbar_button_color="#555B66", scrollbar_button_hover_color="#64748B")
    theme["CTkFrame"].update(fg_color=PANEL, top_fg_color="#22252B", border_color=BORDER, corner_radius=10)
    theme["CTkLabel"].update(text_color=TEXT)
    theme["CTkSlider"].update(button_color=GOLD, button_hover_color="#F4CE73", progress_color=GOLD)
    theme["CTkScrollbar"].update(button_color="#33373F", button_hover_color="#64748B")
