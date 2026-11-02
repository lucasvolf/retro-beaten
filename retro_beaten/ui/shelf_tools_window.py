"""Personalization and export tools, kept outside the main shelf toolbar."""

from pathlib import Path
from copy import deepcopy
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel
from retro_beaten.services.shelf_tools import SECTION_NAMES, section_order, save_background
from retro_beaten.services.export_job import ExportJob


class ShelfToolsWindow(ManagedToplevel):
    def __init__(self, app):
        super().__init__(app.window, fg_color="#101114")
        self.app = app
        self.title("Shelf tools - Retro Beaten")
        self.geometry("620x680")
        self.minsize(580, 620)
        self.transient(app.window)
        self.poll_id = None
        self.export_job = None
        self.close_when_done = False
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.busy = False
        ctk.CTkLabel(self, text="Make the shelf yours", font=("Segoe UI", 24, "bold"),
                     text_color="#E7B84B").pack(pady=16)
        ctk.CTkButton(self, text="Collection overview", command=app.open_overview).pack(fill="x", padx=24, pady=(0, 8))
        background = ctk.CTkFrame(self)
        background.pack(fill="x", padx=24, pady=8)
        ctk.CTkButton(background, text="Choose background", command=self.choose_background).pack(side="left", padx=10, pady=10)
        ctk.CTkButton(background, text="Remove background", command=self.remove_background).pack(side="left", padx=10)
        ctk.CTkLabel(self, text="Background darkness").pack()
        self.darkness = ctk.CTkSlider(self, from_=0, to=90, number_of_steps=18)
        self.darkness.set(app.preferences.get("background_darkness", 65))
        self.darkness.pack(fill="x", padx=30)
        self.darkness.bind("<ButtonRelease-1>", self.apply_darkness, add="+")
        ctk.CTkLabel(self, text="Section order - select a shelf, then move it").pack(pady=(16, 6))
        self.order = section_order(app.preferences.get("section_order", []))
        self.listbox = tk.Listbox(self, bg="#191B20", fg="#F1F2F4", selectbackground="#555B66",
                                 font=("Segoe UI", 11), exportselection=False, height=9)
        self.listbox.pack(fill="both", expand=True, padx=24)
        self.redraw_order(0)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=8)
        for label, delta in (("Move up", -1), ("Move down", 1)):
            ctk.CTkButton(actions, text=label, command=lambda d=delta: self.move(d)).pack(side="left", padx=6)
        export = ctk.CTkFrame(self, fg_color="transparent")
        export.pack(fill="x", padx=24, pady=12)
        self.scope = ctk.CTkOptionMenu(export, values=["Beaten only", "Entire collection"])
        self.scope.pack(side="left")
        self.export_button = ctk.CTkButton(export, text="Export shelf as PNG", command=self.start_export)
        self.export_button.pack(side="right")
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.cancel_button = ctk.CTkButton(self, text="Cancel export", command=self.cancel_export)
        self.message = ctk.CTkLabel(self, text="Drag a cover onto the main window to add a game.", wraplength=550)
        self.message.pack(padx=20, pady=(0, 14))

    def redraw_order(self, index):
        self.listbox.delete(0, "end")
        for key in self.order:
            self.listbox.insert("end", SECTION_NAMES[key])
        self.listbox.selection_set(index)
        self.listbox.see(index)

    def move(self, delta):
        selected = self.listbox.curselection()
        if not selected:
            return
        index = selected[0]
        target = index + delta
        if not 0 <= target < len(self.order):
            return
        self.order[index], self.order[target] = self.order[target], self.order[index]
        self.redraw_order(target)
        self.app.change_view("section_order", list(self.order))

    def choose_background(self):
        filename = filedialog.askopenfilename(parent=self, title="Choose background",
                    filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not filename:
            return
        try:
            save_background(filename, self.app.project_dir)
        except (OSError, ValueError) as error:
            messagebox.showerror("Background", f"Could not load this image: {error}", parent=self)
            return
        self.app.preferences["background_enabled"] = True
        self.apply_darkness()

    def remove_background(self):
        self.app.preferences["background_enabled"] = False
        self.app.persist_preferences()
        self.app.update_background()

    def apply_darkness(self, event=None):
        self.app.preferences["background_darkness"] = round(self.darkness.get())
        self.app.persist_preferences()
        self.app.update_background()

    def start_export(self):
        if self.busy:
            return
        filename = filedialog.asksaveasfilename(parent=self, title="Export shelf",
                    defaultextension=".png", initialfile="RetroBeaten-shelf.png", filetypes=[("PNG image", "*.png")])
        if not filename:
            return
        # Never overwrite a live cover or the locally stored background.
        target = Path(filename).resolve()
        protected = {Path(game["cover_path"]).resolve() for game in self.app.games}
        protected.add((self.app.project_dir / "data/background.png").resolve())
        if target in protected or target.suffix.lower() != ".png":
            messagebox.showerror("Export shelf", "Choose a new PNG file outside your collection covers.", parent=self)
            return
        games = [dict(game) for game in self.app.games]
        try:
            self.export_job = ExportJob(games, target, deepcopy(self.app.preferences), self.scope.get())
        except Exception as error:
            self.message.configure(text=f"Could not start export: {error}")
            return
        self.busy = True
        self.export_button.configure(state="disabled")
        self.message.configure(text="Starting export...")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=24, pady=6, before=self.message)
        self.cancel_button.configure(state="normal", text="Cancel export")
        self.cancel_button.pack(pady=4, before=self.message)
        self.poll_id = self.after(50, self.poll)

    def cancel_export(self):
        if self.export_job is not None:
            self.export_job.cancel()
            self.cancel_button.configure(state="disabled", text="Cancelling...")
            self.message.configure(text="Cancelling export...")

    def poll(self):
        self.poll_id = None
        job = self.export_job
        terminal = None
        for kind, value in job.messages():
            if kind == "progress":
                done, total, text = value
                self.progress.set(0.95 * done / max(1, total))
                if not job.cancellation.is_set():
                    self.message.configure(text=text)
            else:
                terminal = (kind, value)
        if terminal is None and not job.process.is_alive():
            # A finished process has flushed its queue; consume the final packet.
            packets = job.messages()
            terminal = next(((kind, value) for kind, value in packets if kind != "progress"),
                            ("error", "The export process stopped unexpectedly. Please try again."))
        if terminal is None:
            self.poll_id = self.after(50, self.poll)
            return
        kind, text = terminal
        self.busy = False
        self.export_job = None
        job.close()
        self.export_button.configure(state="normal")
        self.cancel_button.pack_forget()
        self.progress.set(1 if kind == "success" else 0)
        self.message.configure(text=text)
        if self.close_when_done:
            self.destroy()

    def close(self):
        if self.busy:
            self.close_when_done = True
            self.cancel_export()
        else:
            self.destroy()

    def destroy(self):
        if self.export_job is not None:
            self.export_job.close()
            self.export_job = None
        if self.poll_id:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
