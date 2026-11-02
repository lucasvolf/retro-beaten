"""A shared, delayed tooltip and lightweight border highlight."""

import tkinter as tk


class CoverTooltip:
    def __init__(self, root):
        self.root = root
        self.pending = None
        self.popup = None
        self.owner = None

    def hide(self):
        if self.pending is not None:
            self.root.after_cancel(self.pending)
            self.pending = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        self.owner = None

    def schedule(self, frame, name, platform):
        if self.owner is frame:
            return
        self.hide()
        self.owner = frame

        def show():
            self.pending = None
            if not frame.winfo_exists() or not frame.winfo_ismapped():
                self.hide()
                return
            self.popup = tk.Toplevel(self.root)
            self.popup.withdraw()
            self.popup.overrideredirect(True)
            self.popup.attributes("-topmost", True)
            box = tk.Frame(self.popup, bg="#2D3037", padx=1, pady=1)
            box.pack()
            tk.Label(box, text=f"{name}\n{platform}", bg="#15171B", fg="#F1F2F4",
                     font=("Segoe UI", 10), padx=12, pady=8, wraplength=260,
                     justify="left").pack()
            self.popup.update_idletasks()
            x = min(frame.winfo_rootx(), self.root.winfo_screenwidth()-self.popup.winfo_reqwidth()-12)
            y = frame.winfo_rooty()+frame.winfo_height()+6
            if y+self.popup.winfo_reqheight() > self.root.winfo_screenheight()-12:
                y = frame.winfo_rooty()-self.popup.winfo_reqheight()-6
            self.popup.geometry(f"+{max(0,x)}+{max(0,y)}")
            self.popup.deiconify()
        self.pending = self.root.after(350, show)


def attach_cover_hover(frame, label, name, platform):
    root = frame.winfo_toplevel()
    if not hasattr(root, "_cover_tooltip"):
        root._cover_tooltip = CoverTooltip(root)
    tooltip = root._cover_tooltip
    original = frame.cget("border_color")
    # Blend the status color towards white, keeping its meaning visible.
    rgb = tuple(int(original[i:i+2], 16) for i in (1,3,5))
    highlight = "#" + "".join(f"{round(value+(255-value)*0.45):02x}" for value in rgb)

    def enter(event=None):
        frame.configure(border_color=highlight)
        tooltip.schedule(frame, name, platform)

    def leave(event=None):
        x, y = frame.winfo_pointerxy()
        if frame.winfo_rootx() <= x < frame.winfo_rootx()+frame.winfo_width() and frame.winfo_rooty() <= y < frame.winfo_rooty()+frame.winfo_height():
            return
        frame.configure(border_color=original)
        if tooltip.owner is frame:
            tooltip.hide()

    def cleanup(event):
        if event.widget in (frame, frame._canvas) and tooltip.owner is frame:
            tooltip.hide()

    for widget in (frame, label):
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
        widget.bind("<Button-1>", lambda event: tooltip.hide(), add="+")
        widget.bind("<Button-3>", lambda event: tooltip.hide(), add="+")
    frame.bind("<Destroy>", cleanup, add="+")
