"""Debounced decorative wallpaper with a dark overlay."""

import tkinter as tk
from PIL import Image, ImageTk, ImageOps, ImageEnhance


class Background:
    def __init__(self, root, header, path, darkness=65):
        self.root, self.header = root, header
        self.source = None
        self.darkness = darkness
        self.pending = None
        self.last_render = None
        self.label = tk.Label(root, borderwidth=0)
        self.header_item = None
        root.bind("<Configure>", self.schedule, add="+")
        root.bind("<Destroy>", self.close, add="+")
        self.load(path, darkness)

    def load(self, path, darkness):
        self.darkness = darkness
        self.last_render = None
        self.source = None
        if path is not None:
            try:
                with Image.open(path) as image:
                    self.source = image.convert("RGB")
            except OSError:
                pass
        if self.source is None:
            self.label.place_forget()
            if self.header_item:
                self.header._canvas.delete(self.header_item)
                self.header_item = None
        else:
            self.label.place(x=0, y=0, relwidth=1, relheight=1)
            self.label.lower()
            self.schedule()

    def schedule(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(150, self.draw)

    def draw(self):
        self.pending = None
        if self.source is None:
            return
        signature = (self.root.winfo_width(), self.root.winfo_height(),
                     self.header.winfo_width(), self.header.winfo_height(), self.darkness)
        if signature == self.last_render:
            return
        self.last_render = signature
        image = ImageOps.fit(self.source, (max(1, self.root.winfo_width()), max(1, self.root.winfo_height())))
        image = ImageEnhance.Brightness(image).enhance(1 - self.darkness / 100)
        self.photo = ImageTk.PhotoImage(image, master=self.root)
        self.label.configure(image=self.photo)
        banner = ImageOps.fit(self.source, (max(1, self.header.winfo_width()), max(1, self.header.winfo_height())))
        banner = ImageEnhance.Brightness(banner).enhance(1 - self.darkness / 100)
        self.banner = ImageTk.PhotoImage(banner, master=self.root)
        if self.header_item:
            self.header._canvas.delete(self.header_item)
        self.header_item = self.header._canvas.create_image(0, 0, anchor="nw", image=self.banner)

    def close(self, event):
        if event.widget is self.root and self.pending:
            self.root.after_cancel(self.pending)
            self.pending = None
