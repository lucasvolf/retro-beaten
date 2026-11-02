"""Lightweight cover items painted together by the viewport canvas."""
from PIL import Image, ImageTk
from tkinter import Menu
from retro_beaten.platforms import PLATFORMS
from retro_beaten.statuses import STATUS_LABELS, STATUS_BORDER_COLORS
from retro_beaten.ui.cover_cache import load_thumbnail
from retro_beaten.ui.cover_hover import CoverTooltip


class CanvasFavorite:
    """Small action handle shared with the rest of the collection UI."""
    def __init__(self, card):
        self.card = card

    def invoke(self):
        card = self.card
        if not card.exhibition and card.on_favorite is not None:
            card.on_favorite(card.game, not bool(card.game.get("favorite")))
            card.repaint_favorite()

    def cget(self, option):
        if option == "state":
            return "disabled" if self.card.exhibition else "normal"
        return "#E7B84B" if self.card.game.get("favorite") else "#64748B"


class CanvasCard:
    def __init__(self, surface, game, size, scale, exhibition, on_status, on_details, on_favorite):
        self.surface, self.game, self.exhibition = surface, game, exhibition
        self.on_favorite = on_favorite
        self.tag = f"card-{id(self)}"
        self.star_tag = f"favorite-{id(self)}"
        self.scale = scale
        self.menu = None
        self.bindings = []
        self.alive = True
        self.bounds = (0, 0, 0, 0)
        self.color = STATUS_BORDER_COLORS[game["status"]]
        unavailable = False
        try:
            image, self.display_size = load_thumbnail(game["cover_path"], size)
        except (OSError, ValueError, Image.DecompressionBombError):
            image = Image.new("RGB", size, "#191B20")
            self.display_size = size
            unavailable = True
        pixel_size = tuple(max(1, round(value*scale)) for value in self.display_size)
        self.photo = ImageTk.PhotoImage(image.resize(pixel_size, Image.Resampling.LANCZOS), master=surface)
        margin = round(3*scale)
        self.width, self.height = pixel_size[0]+margin*2, pixel_size[1]+margin*2
        self.border = surface.create_rectangle(0, 0, self.width, self.height,
                                               fill=self.color, outline="", tags=self.tag)
        self.image_item = surface.create_image(margin, margin, image=self.photo, anchor="nw", tags=self.tag)
        if unavailable:
            surface.create_text(self.width/2, self.height/2, text="Cover unavailable",
                                fill="#969BA5", width=max(40, self.width-16), tags=self.tag)
        self.star = None
        if game["status"] != "recommended":
            side, inset = round(28*scale), round(6*scale)
            self.star_box = (self.width-inset-side, self.height-inset-side,
                             self.width-inset, self.height-inset)
            surface.create_rectangle(*self.star_box, fill="#15171B", outline="",
                                     tags=(self.star_tag, self.tag))
            self.star = surface.create_text(self.width-inset-side/2, self.height-inset-side/2,
                                           text="★", font=("Segoe UI Symbol", -round(23*scale)),
                                           tags=(self.star_tag, self.tag))
            self.favorite_star = CanvasFavorite(self)
            self.repaint_favorite()
        root = surface.winfo_toplevel()
        if not hasattr(root, "_cover_tooltip"):
            root._cover_tooltip = CoverTooltip(root)
        self.tooltip = root._cover_tooltip
        if not exhibition:
            self.bind(self.tag, "<Button-1>", lambda event: self.open_details(on_details))
            self.bind(self.tag, "<Button-3>", lambda event: self.show_menu(event, on_status))
            self.bind(self.tag, "<Enter>", self.enter)
            self.bind(self.tag, "<Leave>", self.leave)
            if self.star is not None:
                self.bind(self.star_tag, "<Button-1>", self.click_favorite)

    def bind(self, tag, event, callback):
        binding = self.surface.tag_bind(tag, event, callback)
        self.bindings.append((tag, event, binding))

    def move(self, center_x, top_y):
        x, y = round(center_x-self.width/2), round(top_y)
        old_x, old_y = self.bounds[:2]
        if self.bounds[2:] == (0, 0):
            old_x = old_y = 0
        self.surface.move(self.tag, x-old_x, y-old_y)
        self.bounds = (x, y, self.width, self.height)

    def repaint_favorite(self):
        if self.star is not None:
            color = "#E7B84B" if self.game.get("favorite") else "#64748B"
            if self.surface.itemcget(self.star, "fill") != color:
                self.surface.itemconfigure(self.star, fill=color)

    def click_favorite(self, event):
        self.tooltip.hide()
        self.favorite_star.invoke()
        return "break"

    def open_details(self, callback):
        self.tooltip.hide()
        callback(self.game)

    def show_menu(self, event, callback):
        self.tooltip.hide()
        if self.menu is None:
            self.menu = Menu(self.surface, tearoff=False)
            options = {f"Mark as {label}": status for status, label in STATUS_LABELS.items()}
            if self.game["status"] == "recommended":
                options = {"Add to Wishlist": "wishlist"}
            for label, status in options.items():
                self.menu.add_command(label=label, command=lambda value=status: callback(self.game, value))
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            if self.menu.winfo_exists():
                self.menu.grab_release()

    def enter(self, event=None):
        rgb = tuple(int(self.color[i:i+2], 16) for i in (1, 3, 5))
        highlight = "#" + "".join(f"{round(v+(255-v)*.45):02x}" for v in rgb)
        self.surface.itemconfigure(self.border, fill=highlight)
        self.surface.configure(cursor="hand2")
        self.tooltip.schedule(self, self.game["name"], PLATFORMS[self.game["platform"]]["name"])

    def leave(self, event=None):
        self.surface.itemconfigure(self.border, fill=self.color)
        self.surface.configure(cursor="")
        if self.tooltip.owner is self:
            self.tooltip.hide()

    # The existing shared tooltip needs only these geometry/lifetime queries.
    def winfo_exists(self):
        return self.alive

    def winfo_ismapped(self):
        x, y, width, height = self.bounds
        return self.alive and self.surface.winfo_ismapped() and y+height > 0 and y < self.surface.winfo_height()

    def winfo_rootx(self):
        return self.surface.winfo_rootx() + self.bounds[0]

    def winfo_rooty(self):
        return self.surface.winfo_rooty() + self.bounds[1]

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def destroy(self):
        if not self.alive:
            return
        self.alive = False
        if self.tooltip.owner is self:
            self.tooltip.hide()
        for tag, event, binding in self.bindings:
            self.surface.tag_unbind(tag, event, binding)
        self.bindings.clear()
        self.surface.delete(self.tag)
        if self.menu is not None:
            self.menu.destroy()
        self.photo = None
