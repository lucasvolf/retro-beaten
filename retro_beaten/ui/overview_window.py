"""Lightweight collection dashboard rendered with Tk, without plotting dependencies."""

import tkinter as tk
import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel
from retro_beaten.services.collection_stats import collection_stats
from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS, STATUS_CODES, STATUS_BORDER_COLORS


class OverviewWindow(ManagedToplevel):
    def __init__(self, parent, get_games):
        super().__init__(parent, fg_color="#101114")
        self.get_games = get_games
        self.title("Collection overview - Retro Beaten")
        self.geometry("900x700")
        self.minsize(720, 560)
        self.transient(parent)
        self.bind("<Escape>", lambda event: self.destroy())
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 16))
        ctk.CTkLabel(heading, text="Your collection, at a glance", text_color="#E7B84B",
                     font=("Segoe UI", 24, "bold")).pack(anchor="w")
        self.total_label = ctk.CTkLabel(heading, text="", text_color="#969BA5", anchor="w")
        self.total_label.pack(anchor="w", pady=(4, 0))
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", padx=24)
        self.count_labels = {}
        for column, (status, name) in enumerate(STATUS_LABELS.items()):
            cards.grid_columnconfigure(column, weight=1, uniform="cards")
            card = ctk.CTkFrame(cards, fg_color="#191B20", border_width=1, border_color="#2D3037")
            card.grid(row=0, column=column, sticky="ew", padx=(0, 8 if column < 3 else 0))
            number = ctk.CTkLabel(card, text="0", font=("Segoe UI", 30, "bold"), text_color=STATUS_BORDER_COLORS[status])
            number.pack(pady=(12, 0))
            ctk.CTkLabel(card, text=name, text_color="#CBD5E1").pack(pady=(0, 12))
            self.count_labels[status] = number
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.grid(row=2, column=0, sticky="ew", padx=24, pady=(22, 10))
        ctk.CTkLabel(filters, text="Games by platform", font=("Segoe UI", 17, "bold")).pack(side="left")
        self.status_menu = ctk.CTkOptionMenu(filters, values=[*STATUS_LABELS.values(), "All statuses"],
                                            command=lambda value: self.draw_chart())
        self.status_menu.set("Beaten")
        self.status_menu.pack(side="right")
        self.chart_area = ctk.CTkScrollableFrame(self, fg_color="#191B20")
        self.chart_area.grid(row=3, column=0, sticky="nsew", padx=24)
        self.chart = tk.Canvas(self.chart_area, bg="#191B20", highlightthickness=0, height=330)
        self.chart.pack(fill="x", expand=True)
        self.chart.bind("<Configure>", lambda event: self.draw_chart())
        ctk.CTkLabel(self, text="Each saved game/platform entry counts once. Recommendations are not included.",
                     text_color="#969BA5", wraplength=650).grid(row=4, column=0, padx=24, pady=(12, 18))
        self.refresh()

    def refresh(self):
        self.stats = collection_stats(self.get_games())
        self.total_label.configure(text=f"{self.stats['total']} games on your shelves  ·  {self.stats['favorites']} favorites")
        for status, label in self.count_labels.items():
            label.configure(text=str(self.stats["statuses"][status]))
        self.draw_chart()

    def draw_chart(self):
        if not hasattr(self, "stats"):
            return
        self.chart.delete("all")
        if not self.stats["total"]:
            self.chart.configure(height=180)
            self.chart.create_text(24, 65, text="Your collection is empty. Add an adventure to get started.",
                                   anchor="w", fill="#969BA5", font=("Segoe UI", 12), width=500)
            return
        status = STATUS_CODES.get(self.status_menu.get())
        codes = sorted(set(PLATFORMS) | set(self.stats["platforms"]))
        rows = [(code, self.stats["platforms"].get(code, {}).get(status, 0) if status else
                 sum(self.stats["platforms"].get(code, {}).values())) for code in codes]
        maximum = max((value for _, value in rows), default=0)
        width = max(400, self.chart.winfo_width())
        start, end = 195, width - 58
        self.chart.configure(height=max(180, len(rows)*46+50))
        for index, (code, count) in enumerate(rows):
            y = 20 + index*46
            name = PLATFORMS.get(code, {}).get("name", code)
            self.chart.create_text(16, y+12, text=name, anchor="w", fill="#CBD5E1", font=("Segoe UI", 11))
            self.chart.create_line(start, y+25, end, y+25, fill="#2D3037")
            if count:
                right = start+(end-start)*count/maximum
                self.chart.create_rectangle(start, y+2, right, y+23, fill=STATUS_BORDER_COLORS.get(status, "#969BA5"), outline="")
            self.chart.create_text(end+14, y+12, text=str(count), anchor="w", fill="#F1F2F4", font=("Segoe UI", 12, "bold"))
        if not maximum:
            self.chart.create_text(16, len(rows)*46+30, text="No games with this status yet.", anchor="w",
                                   fill="#969BA5", font=("Segoe UI", 11))
