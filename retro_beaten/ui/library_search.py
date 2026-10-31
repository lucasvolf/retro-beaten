"""Search field that filters only the local collection."""

import customtkinter as ctk


class LibrarySearch(ctk.CTkFrame):
    def __init__(self, parent, on_change):
        super().__init__(parent, fg_color="transparent")
        self.on_change = on_change
        self.pending_id = None
        self.query = ctk.StringVar(master=self, value="")
        self.entry = ctk.CTkEntry(
            self, textvariable=self.query, placeholder_text="Search collection",
            fg_color="#1E293B", border_color="#374151", text_color="#F8FAFC",
            height=36
        )
        # A visible label identifies the field even when it contains text.
        ctk.CTkLabel(self, text="Search collection", text_color="#94A3B8").pack(anchor="w")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        ctk.CTkButton(
            self, text="Clear", width=80, command=self.clear,
            fg_color="#374151", hover_color="#475569"
        ).pack(side="right")
        self.trace_id = self.query.trace_add("write", self.schedule_search)

    def get_query(self):
        return self.query.get()

    def clear(self):
        self.query.set("")

    def schedule_search(self, *args):
        if self.pending_id is not None:
            self.after_cancel(self.pending_id)
        # Wait for a short typing pause instead of rebuilding on every keystroke.
        self.pending_id = self.after(250, self.notify_change)

    def notify_change(self):
        self.pending_id = None
        self.on_change()

    def destroy(self):
        if self.pending_id is not None:
            self.after_cancel(self.pending_id)
        self.query.trace_remove("write", self.trace_id)
        super().destroy()
