"""Display controls usable in the sidebar or a compact horizontal toolbar."""
import customtkinter as ctk
from retro_beaten.storage.preferences import COVER_SIZES, SORT_ORDERS
from retro_beaten.ui.theme import MUTED


class ViewControls(ctk.CTkFrame):
    def __init__(self, parent, preferences, on_change, on_exhibition, on_tools=None, on_pick=None, vertical=False):
        super().__init__(parent, fg_color="transparent")
        if vertical:
            self.grid_columnconfigure(0, weight=1)
        size_label = ctk.CTkLabel(self, text="Cover size", text_color=MUTED, anchor="w")
        sort_label = ctk.CTkLabel(self, text="Sort by", text_color=MUTED, anchor="w")
        self.size_menu = ctk.CTkOptionMenu(self, values=list(COVER_SIZES), width=90,
                                         command=lambda value: on_change("cover_size", value))
        self.size_menu.set(preferences["cover_size"])
        self.sort_menu = ctk.CTkOptionMenu(self, values=list(SORT_ORDERS), width=130,
                                         command=lambda value: on_change("sort_order", value))
        self.sort_menu.set(preferences["sort_order"])
        for index, widget in enumerate((size_label, self.size_menu, sort_label, self.sort_menu)):
            widget.grid(row=index if vertical else 0, column=0 if vertical else index,
                        sticky="ew", padx=4, pady=(4, 2) if vertical else 0)
        extra = ctk.CTkFrame(self, fg_color="transparent")
        extra.grid(row=4 if vertical else 0, column=0 if vertical else 4, sticky="ew", pady=(12, 0) if vertical else 0)
        for label, command in (("Shelf tools", on_tools), ("What should I play?", on_pick), ("Exhibition mode", on_exhibition)):
            if command:
                ctk.CTkButton(extra, text=label, command=command, width=90, height=32,
                              font=("Segoe UI", 12), border_width=0).pack(
                    side="top" if vertical else "left", fill="x", padx=4, pady=3)
