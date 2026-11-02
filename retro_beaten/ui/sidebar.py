"""Collapsible library navigation; controls stay separate from shelf rendering."""
import customtkinter as ctk
from retro_beaten.ui.theme import GOLD, MUTED, TEXT
from retro_beaten.ui.cover_hover import CoverTooltip

SHELVES = (("all", "All games", "▦"), ("playing", "Playing", "▷"),
           ("beaten", "Beaten", "✓"), ("wishlist", "Wishlist", "♡"),
           ("recommended", "Recommended", "✦"), ("dropped", "Dropped", "−"))


class Sidebar(ctk.CTkFrame):
    def __init__(self, parent, expanded, on_toggle, on_select, on_search, on_manual,
                 on_backup, on_tools, on_overview):
        super().__init__(parent, width=248, fg_color="#141519", corner_radius=0,
                         border_width=0)
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.on_toggle = on_toggle
        self.expanded = expanded
        self.selected = "all"
        self.counts = {}
        top = ctk.CTkFrame(self, fg_color="transparent", height=78)
        top.grid(row=0, column=0, sticky="ew")
        top.pack_propagate(False)
        self.toggle_button = ctk.CTkButton(top, text="☰", width=38, height=38,
            font=("Segoe UI", 20), fg_color="transparent", border_width=0,
            command=self.toggle)
        self.toggle_button.pack(side="left", padx=(12, 4))
        self.identity = ctk.CTkLabel(top, text="RETRO BEATEN", font=("Segoe UI", 18, "bold"), text_color=GOLD)
        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0,
                                          scrollbar_button_color="#24272D")
        self.body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 12))
        self.rail = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons, self.rail_buttons = {}, {}
        self.caption("LIBRARY")
        for key, label, icon in SHELVES:
            command = lambda value=key: on_select(value)
            self.buttons[key] = self.button(self.body, f"{icon}    {label}", command)
            self.rail_buttons[key] = self.button(self.rail, icon, command, compact=True)
            self.hint(self.rail_buttons[key], label)
        self.caption("ADD TO COLLECTION")
        self.search_button = self.button(self.body, "+    Search IGDB", on_search, primary=True)
        self.manual_button = self.button(self.body, "＋    Add manually", on_manual)
        self.settings = ctk.CTkFrame(self.body, fg_color="transparent")
        self.settings.pack(fill="x", pady=(10, 0))
        # View settings and refresh controls are inserted here by the app.
        self.tools = ctk.CTkFrame(self.body, fg_color="transparent")
        self.tools.pack(fill="x")
        ctk.CTkLabel(self.tools, text="TOOLS", anchor="w", font=("Segoe UI", 10, "bold"),
                     text_color=MUTED).pack(fill="x", padx=10, pady=(18, 5))
        for label, command in (("Collection overview", on_overview), ("Shelf tools", on_tools),
                               ("Backup and restore", on_backup)):
            self.button(self.tools, label, command)
        ctk.CTkLabel(self.body, text="A Collection of Adventures,\nNot Achievements.",
                     font=("Segoe UI", 10), text_color=MUTED, justify="left").pack(anchor="w", padx=10, pady=24)
        ctk.CTkFrame(self.rail, height=1, fg_color="#2D3037").pack(fill="x", padx=8, pady=12)
        for icon, label, command in (("+", "Search IGDB", on_search), ("✎", "Add manually", on_manual),
                                     ("⚙", "Shelf tools", on_tools)):
            button = self.button(self.rail, icon, command, compact=True)
            self.hint(button, label)
        self.apply_expansion()

    def caption(self, text):
        ctk.CTkLabel(self.body, text=text, anchor="w", font=("Segoe UI", 10, "bold"),
                     text_color=MUTED).pack(fill="x", padx=10, pady=(14, 6))

    @staticmethod
    def button(parent, text, command, compact=False, primary=False):
        button = ctk.CTkButton(parent, text=text, command=command, height=36,
            width=40 if compact else 190, anchor="center" if compact else "w",
            font=("Segoe UI", 19 if compact else 12), border_width=0, corner_radius=6,
            fg_color=GOLD if primary else "transparent", hover_color="#F4CE73" if primary else "#24272D",
            text_color="#101114" if primary else TEXT)
        button.pack(fill="x", padx=4, pady=2)
        return button

    def hint(self, button, label):
        root = self.winfo_toplevel()
        if not hasattr(root, "_cover_tooltip"):
            root._cover_tooltip = CoverTooltip(root)
        tooltip = root._cover_tooltip
        button.bind("<Enter>", lambda event: tooltip.schedule(button, label, ""), add="+")
        button.bind("<Leave>", lambda event: tooltip.hide(), add="+")
        button.bind("<Button-1>", lambda event: tooltip.hide(), add="+")

    def toggle(self):
        self.expanded = not self.expanded
        self.apply_expansion()
        self.on_toggle(self.expanded)

    def apply_expansion(self):
        self.winfo_toplevel()._cover_tooltip.hide()
        self.configure(width=248 if self.expanded else 64)
        if self.expanded:
            self.rail.grid_remove()
            self.body.grid()
            self.identity.pack(side="left")
        else:
            self.body.grid_remove()
            self.identity.pack_forget()
            self.rail.grid(row=1, column=0, sticky="new", padx=8)

    def update_selection(self, selected, games, recommendations):
        self.selected = selected
        counts = {key: sum(g["status"] == key for g in games) for key, _, _ in SHELVES}
        counts.update(all=len(games), recommended=len(recommendations))
        for key, label, icon in SHELVES:
            text = f"{icon}    {label}   {counts[key]}"
            if self.buttons[key].cget("text") != text:
                self.buttons[key].configure(text=text)
            for button in (self.buttons[key], self.rail_buttons[key]):
                button.configure(fg_color="#2B2820" if key == selected else "transparent",
                                 text_color=GOLD if key == selected else MUTED)
        self.counts = counts
