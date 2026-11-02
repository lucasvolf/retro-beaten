"""Export and restore while keeping the interface responsive."""

from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import filedialog, messagebox
import sqlite3

import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel

from retro_beaten.services.backup import create_backup, restore_backup


class BackupWindow(ManagedToplevel):
    def __init__(self, parent, database_path, project_dir, on_restored):
        super().__init__(parent, fg_color="#101114")
        self.database_path = database_path
        self.project_dir = project_dir
        self.on_restored = on_restored
        self.busy = False
        self.results = Queue()
        self.poll_id = None
        self.title("Backup and restore — Retro Beaten")
        self.geometry("620x440")
        self.minsize(560, 440)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda event: self.close())

        ctk.CTkLabel(self, text="Back up your shelf", font=("Segoe UI", 24, "bold"),
                     text_color="#E7B84B").pack(anchor="w", padx=24, pady=(24, 12))
        ctk.CTkLabel(
            self, text="Export your saved games and covers in a single ZIP file.\n"
            "Restore them here or in another Retro Beaten installation.",
            text_color="#F1F2F4", justify="left", wraplength=510,
        ).pack(anchor="w", padx=24, pady=(0, 20))
        self.export_button = ctk.CTkButton(
            self, text="Create backup...", command=self.export,
            fg_color="#E7B84B", hover_color="#C99B35", text_color="#101114",
        )
        self.export_button.pack(anchor="w", padx=24, pady=(0, 12))
        self.restore_button = ctk.CTkButton(
            self, text="Restore backup...", command=self.restore,
            fg_color="#24272D", hover_color="#33373F",
        )
        self.restore_button.pack(anchor="w", padx=24)
        self.close_button = ctk.CTkButton(
            self, text="Close", command=self.close, fg_color="#24272D", hover_color="#33373F",
        )
        self.close_button.pack(side="bottom", anchor="e", padx=24, pady=20)
        self.message = ctk.CTkLabel(
            self, text="Restoring replaces your current collection. Before proceeding, the app\n"
            "automatically saves a copy in the backups folder.",
            text_color="#969BA5", justify="left", wraplength=510, anchor="w",
        )
        self.message.pack(fill="both", expand=True, padx=24, pady=(16, 0))
        # Prevent collection edits while files are being copied.
        self.grab_set()

    def export(self):
        if self.busy:
            return
        filename = filedialog.asksaveasfilename(
            parent=self, title="Save collection backup", defaultextension=".zip",
            initialfile=f"Retro-Beaten-{datetime.now():%Y-%m-%d-%H%M%S}.zip",
            filetypes=[("Retro Beaten backup", "*.zip")],
        )
        if filename:
            self.start("export", Path(filename))

    def restore(self):
        if self.busy:
            return
        filename = filedialog.askopenfilename(
            parent=self, title="Select backup", filetypes=[("Retro Beaten backup", "*.zip")],
        )
        if not filename:
            return
        if messagebox.askyesno(
            "Replace your collection?",
            f"Restore the collection from:\n{filename}\n\n"
            "Your current games will be replaced by this backup; the collections will not be merged.\n\n"
            "A copy of your current collection will be saved in the backups folder before replacement.",
            parent=self, icon="warning", default="no",
        ):
            self.start("restore", Path(filename))

    def start(self, operation, path):
        self.busy = True
        for button in (self.export_button, self.restore_button, self.close_button):
            button.configure(state="disabled")
        self.message.configure(text="Creating backup..." if operation == "export" else "Checking and restoring the backup...")
        Thread(target=self.work, args=(operation, path), daemon=True).start()
        self.poll_id = self.after(100, self.poll)

    def work(self, operation, path):
        # This thread never accesses widgets; it returns results through the queue.
        try:
            service = create_backup if operation == "export" else restore_backup
            result = service(self.database_path, self.project_dir, path)
        except (ValueError, OSError, sqlite3.Error) as error:
            self.results.put(("error", str(error), path))
        except Exception:
            self.results.put(("error", "Could not complete the operation. Check the file and try again.", path))
        else:
            self.results.put((operation, result, path))

    def poll(self):
        self.poll_id = None
        try:
            operation, result, path = self.results.get_nowait()
        except Empty:
            self.poll_id = self.after(100, self.poll)
            return
        self.busy = False
        for button in (self.export_button, self.restore_button, self.close_button):
            button.configure(state="normal")
        if operation == "error":
            self.message.configure(text=f"Operation not completed.\n{result}")
        elif operation == "export":
            self.message.configure(text=f"Backup created with {result} games.\n{path}")
        else:
            self.on_restored()
            self.message.configure(text=f"Collection restored: {result['count']} games.\n"
                                   f"Previous collection backup: {result['safety_backup']}")

    def close(self):
        if not self.busy:
            self.destroy()

    def destroy(self):
        if self.poll_id is not None:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
