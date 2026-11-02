"""Shared hover popup lifetime and border stability."""

import tempfile
import unittest
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from retro_beaten.ui.cover_card import create_cover
from retro_beaten.ui.cover_hover import attach_cover_hover


class HoverTests(unittest.TestCase):
    def test_popup_cleanup_on_cover_destruction(self):
        root = ctk.CTk()
        root.attributes("-alpha", 0)
        try:
            with tempfile.TemporaryDirectory() as folder:
                cover = Path(folder) / "cover.png"
                Image.new("RGB", (150, 200), "navy").save(cover)
                frame, label = create_cover(root, cover, (150, 200), "beaten")
                frame.pack()
                attach_cover_hover(frame, label, "Adventure", "PlayStation 1")
                root.update()
                root._cover_tooltip.schedule(frame, "Adventure", "PlayStation 1")
                root.after(400, root.quit)
                root.mainloop()
                self.assertIsNotNone(root._cover_tooltip.popup)
                self.assertEqual(label.cget("image").cget("size"), (150, 200))
                frame.destroy()
                self.assertIsNone(root._cover_tooltip.popup)
                self.assertIsNone(root._cover_tooltip.pending)
        finally:
            for callback in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", callback)
            root.destroy()
