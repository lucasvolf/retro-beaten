"""Local name and description editor."""

import sqlite3

import customtkinter as ctk


class EditGameWindow(ctk.CTkToplevel):
    def __init__(self, parent, game, on_save):
        super().__init__(parent, fg_color="#111827")
        self.game = game
        self.on_save = on_save
        self.title("Edit game — Retro Beaten")
        self.geometry("620x520")
        self.minsize(480, 440)
        self.transient(parent)
        self.bind("<Escape>", lambda event: self.destroy())

        ctk.CTkLabel(self, text="Edit game", font=("Segoe UI", 22, "bold"),
                     text_color="#E7B84B").pack(anchor="w", padx=24, pady=(20, 12))
        ctk.CTkLabel(self, text="Game name", text_color="#F8FAFC").pack(anchor="w", padx=24)
        self.name_entry = ctk.CTkEntry(self)
        self.name_entry.pack(fill="x", padx=24, pady=(0, 12))
        self.name_entry.insert(0, game["name"])
        ctk.CTkLabel(self, text="Description (optional)", text_color="#F8FAFC").pack(anchor="w", padx=24)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=20)
        self.cancel_button = ctk.CTkButton(
            footer, text="Cancel", command=self.destroy,
            fg_color="#374151", hover_color="#475569",
        )
        self.cancel_button.pack(side="left")
        self.save_button = ctk.CTkButton(
            footer, text="Save", command=self.save,
            fg_color="#E7B84B", hover_color="#C99B35", text_color="#111827",
        )
        self.save_button.pack(side="right")
        self.message = ctk.CTkLabel(self, text="Changes will be saved to your local collection.",
                                    text_color="#94A3B8", wraplength=420)
        self.message.pack(side="bottom", fill="x", padx=24, pady=(12, 0))
        self.summary_box = ctk.CTkTextbox(self, wrap="word", fg_color="#1E293B",
                                         text_color="#F8FAFC", font=("Segoe UI", 15))
        self.summary_box.pack(fill="both", expand=True, padx=24)
        self.summary_box.insert("1.0", game.get("summary") or "")

    def save(self):
        self.save_button.configure(state="disabled")
        try:
            self.on_save(self.game, self.name_entry.get(), self.summary_box.get("1.0", "end-1c"))
        except ValueError as error:
            self.message.configure(text=str(error))
        except (OSError, sqlite3.Error):
            self.message.configure(text="Could not save. Your text is still here; please try again.")
        else:
            self.destroy()
            return
        self.save_button.configure(state="normal")
