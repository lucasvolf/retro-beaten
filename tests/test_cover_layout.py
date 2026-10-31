"""Regression: displaced images after rendering a large section on Windows."""

import unittest
import tempfile
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from retro_beaten.ui.library_view import create_library_area, render_library


class CoverLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = ctk.CTk()
        self.root.geometry("1920x900")
        self.root.attributes("-alpha", 0)
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.addCleanup(self.close_root)

    def close_root(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()

    def settle_layout(self):
        self.root.update()
        self.root.after(200, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.errors, [])

    def assert_covers_inside_frames(self, area):
        for section in area.winfo_children():
            panel = next(child for child in section.winfo_children()
                         if isinstance(child, ctk.CTkFrame))
            for frame in panel.winfo_children():
                label = frame.winfo_children()[0]
                # winfo_y() alone missed the error: it returned 3 even
                # when the actual screen position matched the border position.
                margin = round(frame._apply_widget_scaling(3))
                self.assertEqual(label.winfo_rootx() - frame.winfo_rootx(), margin,
                                 (frame.winfo_geometry(), label.winfo_geometry(),
                                  frame.winfo_rooty(), label.winfo_rooty(), area._parent_canvas.yview()))
                self.assertEqual(label.winfo_rooty() - frame.winfo_rooty(), margin)
                self.assertEqual(frame.winfo_height() - label.winfo_height(), 2 * margin)
                self.assertEqual(frame._canvas.winfo_rooty(), frame.winfo_rooty())
                self.assertEqual(label._label.winfo_rooty(), label.winfo_rooty())
                self.assertEqual(label._label.winfo_rootx(), label.winfo_rootx())
                self.assertEqual(label._label.winfo_height(), label.winfo_height())
                self.assertEqual(label._label.winfo_width(), label.winfo_width())

    def test_cover_geometry_below_large_section(self):
        cover_path = Path(self.temp.name) / "cover.jpg"
        Image.new("RGB", (300, 400), "navy").save(cover_path)
        games = [
            dict(id=i, name=f"Game {i}", platform="PC" if i < 170 else "PS1",
                 status="beaten", cover_path=cover_path)
            for i in range(184)
        ]
        area = create_library_area(self.root)
        render_library(area, games, lambda *args: None, lambda *args: None)
        self.settle_layout()
        area._parent_canvas.yview_moveto(1)
        self.settle_layout()
        self.assert_covers_inside_frames(area)

        # Resizing and collapsing/expanding must not displace the inner image.
        self.root.geometry("1100x700")
        self.settle_layout()
        area._parent_canvas.yview_moveto(1)
        self.settle_layout()
        self.assert_covers_inside_frames(area)
        first_section = area.winfo_children()[0]
        toggle = next(child for child in first_section.winfo_children()
                      if isinstance(child, ctk.CTkButton))
        for _ in range(2):
            toggle.invoke()
            self.settle_layout()
        self.assert_covers_inside_frames(area)

        # Search rebuilds sections; old callbacks must be cancelled.
        area._parent_canvas.yview_moveto(0)
        for section in area.winfo_children():
            section.destroy()
        render_library(area, games[-14:], lambda *args: None, lambda *args: None)
        self.settle_layout()
        self.assert_covers_inside_frames(area)
        render_library(area, games[-2:], lambda *args: None, lambda *args: None)
        for section in area.winfo_children():
            section.destroy()
        self.settle_layout()
