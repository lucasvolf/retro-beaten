"""Viewport rendering with one painted surface and bounded nearby cover items."""
from math import ceil, floor
from time import perf_counter
import tkinter as tk

from retro_beaten.ui.cover_cache import cover_signature
from retro_beaten.ui.canvas_card import CanvasCard
from retro_beaten.ui.shelf_icons import icon_pixels
from PIL import ImageTk


def rounded_box(left, top, right, bottom, radius):
    radius = min(radius, (right-left)/2, (bottom-top)/2)
    return (left+radius, top, right-radius, top, right, top, right, top+radius,
            right, bottom-radius, right, bottom, right-radius, bottom,
            left+radius, bottom, left, bottom, left, bottom-radius,
            left, top+radius, left, top)


class ShelfViewport:
    """One coalesced scroll/resize observer for the whole library."""

    def __init__(self, area):
        self.area = area
        self.canvas = area._parent_canvas
        self.shelves = set()
        self.pending = None
        self.closed = False
        # A sibling surface is unaffected by the native canvas pixel-copy scroll.
        # Child windows inside that canvas leave torn images on Windows.
        self.surface = tk.Canvas(self.canvas.master, bg="#101114", borderwidth=0, highlightthickness=0)
        self.surface_geometry = None
        original_filter = area._check_if_valid_scroll
        def valid_scroll(widget):
            current = widget
            while current is not None:
                if current is self.surface:
                    return True
                current = getattr(current, "master", None)
            return original_filter(widget)
        self.original_filter = original_filter
        area._check_if_valid_scroll = valid_scroll
        original = self.canvas.cget("yscrollcommand")
        self.last_region = None
        self.last_fractions = None
        self.empty_item = None

        def scrolled(*fractions):
            region = self.canvas.cget("scrollregion")
            current = tuple(map(float, fractions))
            if current != self.last_fractions:
                tooltip = getattr(self.surface.winfo_toplevel(), "_cover_tooltip", None)
                if tooltip is not None:
                    tooltip.hide()
            # If a pending layout grows the scroll region, keep a user who has
            # just reached the bottom there. Explicit moves to the top win.
            if (self.last_region != region and self.last_fractions
                    and self.last_fractions[0] > 0 and self.last_fractions[1] >= .999999
                    and current[0] > 0):
                self.canvas.yview_moveto(1)
            self.last_region, self.last_fractions = region, current
            if original:
                self.canvas.tk.call(*self.canvas.tk.splitlist(original), *fractions)
            self.schedule()

        # Floating canvas windows must not enlarge the logical scroll region.
        area.bind("<Configure>", lambda event: self.canvas.configure(
            scrollregion=self.canvas.bbox(area._create_window_id)))
        self.canvas.configure(yscrollcommand=scrolled)
        for event_name in ("<Configure>", "<Map>"):
            self.canvas.bind(event_name, lambda event: self.sync_surface(), add="+")
        self.sync_surface()
        self.canvas.bind("<Destroy>", self.close, add="+")

    def set_empty_message(self, text=None):
        if self.empty_item is not None:
            self.surface.delete(self.empty_item)
            self.empty_item = None
        if text:
            self.empty_item = self.surface.create_text(0, 0, text=text, fill="#969BA5", anchor="n")
        self.schedule()

    def sync_surface(self):
        if self.closed:
            return
        geometry = (self.canvas.winfo_x(), self.canvas.winfo_y(),
                    self.canvas.winfo_width(), self.canvas.winfo_height())
        if geometry != self.surface_geometry:
            self.surface.place(x=geometry[0], y=geometry[1], width=geometry[2], height=geometry[3])
            self.surface.tk.call("raise", self.surface._w, self.canvas._w)
            self.surface_geometry = geometry
        self.schedule()

    def schedule(self):
        if not self.closed and self.pending is None:
            self.pending = self.canvas.after(16, self.refresh)

    def refresh(self):
        self.pending = None
        if self.empty_item is not None:
            scale = self.area._get_widget_scaling()
            self.surface.coords(self.empty_item, self.canvas.winfo_width()/2,
                                30*scale-self.canvas.canvasy(0))
            self.surface.itemconfigure(self.empty_item, width=min(560*scale, self.canvas.winfo_width()-40),
                                       font=("Segoe UI", -round(13*scale)))
        for shelf in tuple(self.shelves):
            if not shelf.closed:
                shelf.refresh()
        if any(shelf.section._rendering for shelf in self.shelves):
            self.schedule()

    def close(self, event=None):
        self.closed = True
        if self.pending is not None:
            self.canvas.after_cancel(self.pending)
            self.pending = None
        self.shelves.clear()
        self.area._check_if_valid_scroll = self.original_filter
        if self.surface.winfo_exists():
            self.surface.destroy()


class VirtualShelf:
    """A fixed-height panel with a bounded set of visible cards and one spare row."""

    def __init__(self, area, panel, games, size, exhibition, on_status, on_details, on_favorite):
        if not hasattr(area, "_shelf_viewport"):
            area._shelf_viewport = ShelfViewport(area)
        self.viewport = area._shelf_viewport
        self.panel = panel
        self.section = panel.master
        self.surface = self.viewport.surface
        self.paint_tag = f"shelf-{id(self)}"
        self.header_tag = f"header-{id(self)}"
        self.backdrop = self.surface.create_polygon(rounded_box(0, 0, 1, 1, 0), smooth=True, splinesteps=12, fill="#191B20", outline="#292C33", tags=self.paint_tag)
        self.header_bg = self.surface.create_polygon(rounded_box(0, 0, 1, 1, 0), smooth=True, splinesteps=12, fill="#191B20", outline="", tags=(self.header_tag, self.paint_tag))
        self.header_text = self.surface.create_text(0, 0, anchor="w", fill="#F1F2F4", tags=(self.header_tag, self.paint_tag))
        self.header_icon = self.surface.create_image(0, 0, anchor="w", tags=(self.header_tag, self.paint_tag))
        self.divider = self.surface.create_line(0, 0, 1, 0, fill="#2D3037", tags=self.paint_tag)
        self.header_visible = False
        self.header_bounds = (0, 0, 0, 0)
        self.icon_scale = None
        self.icon_photo = None
        self.header_bindings = [
            ("<Button-1>", self.surface.tag_bind(self.header_tag, "<Button-1>",
                lambda event: self.section._title_button.invoke())),
            ("<Enter>", self.surface.tag_bind(self.header_tag, "<Enter>",
                lambda event: self.header_hover(True))),
            ("<Leave>", self.surface.tag_bind(self.header_tag, "<Leave>",
                lambda event: self.header_hover(False))),
        ]
        self.games = games
        self.size = size
        self.exhibition = exhibition
        self.on_status, self.on_details, self.on_favorite = on_status, on_details, on_favorite
        self.cards = {}
        self.positions = {}
        self.reconcile_ids = set()
        self.closed = False
        self.view_key = None
        self.height = None
        self.placeholder_height = None
        self.message_label = None
        panel.pack_propagate(False)
        panel.grid_propagate(False)
        self.section._cards = self.cards
        self.section._covers_panel = panel
        self.section._virtual_shelf = self
        self.section._update_records = self.update_records
        self.section._visibility_changed = self.invalidate
        self.section._cancel_render = self.close
        self.section._rendering = True
        for event_name in ("<Configure>", "<Map>", "<Unmap>"):
            panel._canvas.bind(event_name, lambda event: self.viewport.schedule(), add="+")
        self.section._canvas.bind("<Destroy>", self.close, add="+")
        self.viewport.shelves.add(self)
        self.viewport.schedule()

    def header_hover(self, active):
        self.surface.itemconfigure(self.header_bg, fill="#24272D" if active else "#191B20")
        self.surface.configure(cursor="hand2" if active else "")

    def invalidate(self):
        if not self.closed:
            self.view_key = None
            self.section._rendering = True
            self.viewport.schedule()

    def update_records(self, games, size, exhibition):
        if self.message_label is not None:
            self.surface.delete(self.message_label)
            self.message_label = None
            self.placeholder_height = None
        self.games, self.size, self.exhibition = games, size, exhibition
        self.invalidate()

    def close(self, event=None):
        if self.closed:
            return
        self.closed = True
        for event, binding in self.header_bindings:
            self.surface.tag_unbind(self.header_tag, event, binding)
        self.surface.delete(self.paint_tag)
        for _, card in self.cards.values():
            card.destroy()
        if self.section._floating_header.winfo_exists():
            self.section._floating_header.destroy()
        self.cards.clear()
        self.section._rendering = False
        self.viewport.shelves.discard(self)

    def show_message(self, text):
        self.placeholder_height = max(48, self.height or 48)
        self.games = []
        for _, frame in self.cards.values():
            frame.destroy()
        self.cards.clear()
        self.positions.clear()
        self.message_label = self.surface.create_text(0, 0, text=text, fill="#969BA5", width=600, tags=self.paint_tag)
        self.invalidate()

    def build(self, game):
        scale = self.panel._get_widget_scaling()
        signature = (id(game), game["name"], game["status"], cover_signature(game["cover_path"]),
                     self.size, self.exhibition, scale)
        previous = self.cards.get(game["id"])
        if previous and previous[0] == signature:
            card = previous[1]
            card.repaint_favorite()
        else:
            if previous:
                previous[1].destroy()
            card = CanvasCard(self.surface, game, self.size, scale, self.exhibition,
                              self.on_status, self.on_details, self.on_favorite)
            self.positions.pop(game["id"], None)
        self.cards[game["id"]] = (signature, card)
        return card

    def refresh(self):
        scale = self.panel._get_widget_scaling()
        if self.section.winfo_width() <= 1:
            # An unmapped panel has no usable width. Reserving one column here
            # creates a huge transient scroll region before geometry settles.
            self.section._rendering = bool(self.viewport.canvas.winfo_ismapped() and self.section.winfo_manager())
            return
        width = (self.panel.winfo_width() / scale if self.panel.winfo_width() > 1
                 else max(1, self.section.winfo_width() / scale - 40))
        cell_width, cell_height = self.size[0] + 26, self.size[1] + 26
        columns = max(1, int(width // cell_width))
        rows = ceil(len(self.games) / columns)
        height = self.placeholder_height or max(1, rows * cell_height)
        if height != self.height:
            self.height = height
            self.panel.configure(height=height)
        canvas = self.viewport.canvas
        # Logical spacers define the scroll range. Visible content is painted
        # together on a fixed canvas, without moving native child windows.
        scroll_y = canvas.canvasy(0)
        section_top = (self.section.winfo_y() - scroll_y) / scale
        top = section_top + self.panel.winfo_y() / scale
        viewport_height = canvas.winfo_height() / scale
        section_mapped = bool(self.section.winfo_manager()) and canvas.winfo_ismapped()
        section_x = self.section.winfo_x() / scale
        section_width = self.section.winfo_width() / scale
        section_height = self.section.winfo_height() / scale
        background_top = max(0, section_top)
        background_bottom = min(viewport_height, section_top + section_height)
        visible = section_mapped and background_bottom > background_top
        self.surface.itemconfigure(self.backdrop, state="normal" if visible else "hidden")
        self.surface.coords(self.backdrop, *rounded_box(section_x*scale, section_top*scale,
                            (section_x+section_width)*scale, (section_top+section_height)*scale, 10*scale))
        self.header_visible = section_mapped and section_top < viewport_height and section_top + 71 > 0
        self.header_bounds = (section_x*scale, section_top*scale, section_width*scale, 71*scale)
        state = "normal" if self.header_visible else "hidden"
        for item in (self.header_bg, self.header_text, self.header_icon, self.divider):
            self.surface.itemconfigure(item, state=state)
        self.surface.coords(self.header_bg, *rounded_box((section_x+12)*scale, (section_top+10)*scale,
                            (section_x+section_width-12)*scale, (section_top+55)*scale, 6*scale))
        self.surface.coords(self.header_icon, (section_x+22)*scale, (section_top+32)*scale)
        self.surface.coords(self.header_text, (section_x+52)*scale, (section_top+32)*scale)
        self.surface.itemconfigure(self.header_text, text=self.section._title_button.cget("text"),
                                   font=("Segoe UI", -round(18*scale), "bold"))
        if self.icon_scale != scale:
            title = self.section._title_button.cget("text")[3:].strip()
            self.icon_photo = ImageTk.PhotoImage(icon_pixels(title).resize((round(22*scale), round(22*scale))), master=self.surface)
            self.surface.itemconfigure(self.header_icon, image=self.icon_photo)
            self.icon_scale = scale
        self.surface.coords(self.divider, (section_x+24)*scale, (section_top+63)*scale,
                            (section_x+section_width-24)*scale, (section_top+63)*scale)
        mapped = section_mapped and bool(self.panel.winfo_manager())
        layer_top, layer_bottom = max(0, top), min(viewport_height, top+height)
        if not mapped or layer_bottom <= layer_top:
            first, last = 0, 0
        else:
            first = max(0, floor(-top / cell_height) - 1)
            last = min(rows, ceil((viewport_height - top) / cell_height) + 1)
        if self.message_label is not None:
            self.surface.itemconfigure(self.message_label, state="normal" if mapped and layer_bottom > layer_top else "hidden")
            self.surface.coords(self.message_label, (section_x+section_width/2)*scale,
                                (layer_top+layer_bottom)/2*scale)
        key = (width, scale, first, last, len(self.games), self.size, self.exhibition, mapped, top, layer_top)
        if key == self.view_key and not self.section._rendering:
            return
        start, stop = first * columns, min(len(self.games), last * columns)
        wanted = {game["id"] for game in self.games[start:stop]}
        for game_id in list(self.cards):
            if game_id not in wanted:
                self.cards.pop(game_id)[1].destroy()
                self.positions.pop(game_id, None)
        if self.view_key is None or self.view_key[1] != scale:
            self.reconcile_ids = wanted.copy()
        else:
            self.reconcile_ids.intersection_update(wanted)
            self.reconcile_ids.update(wanted.difference(self.cards))
        self.view_key = key
        # Move every retained card before yielding. Partial movement tears rows
        # apart during wheel scrolling, even when individual positions are right.
        placements = {}
        for index in range(start, stop):
            game = self.games[index]
            row, column = divmod(index, columns)
            row_count = min(columns, len(self.games) - row * columns)
            panel_x = (self.section.winfo_x()+self.panel.winfo_x())/scale
            position = ((panel_x+(width-row_count*cell_width)/2+(column+.5)*cell_width)*scale,
                        (top+row*cell_height+10)*scale)
            placements[game["id"]] = position
            if game["id"] in self.cards and self.positions.get(game["id"]) != position:
                self.cards[game["id"]][1].move(*position)
                self.positions[game["id"]] = position

        deadline = perf_counter() + .008
        self.section._rendering = False
        for index in range(start, stop):
            game = self.games[index]
            if game["id"] not in self.reconcile_ids and game["id"] in self.cards:
                continue
            frame = self.build(game)
            self.reconcile_ids.discard(game["id"])
            position = placements[game["id"]]
            if self.positions.get(game["id"]) != position:
                frame.move(*position)
                self.positions[game["id"]] = position
            if perf_counter() >= deadline and self.reconcile_ids:
                self.section._rendering = True
                return
        self.view_key = key



def create_virtual_section(parent, games, title, on_status, on_details, size,
                           expanded, on_toggle, exhibition, on_favorite):
    from retro_beaten.ui.library_view import create_section
    if not hasattr(parent, "_shelf_viewport"):
        parent._shelf_viewport = ShelfViewport(parent)
    panel = create_section(parent, title, expanded, on_toggle, floating_header=True)
    VirtualShelf(parent, panel, games, size, exhibition, on_status, on_details, on_favorite)
    return panel.master
