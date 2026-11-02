"""Regression: closing a window must cancel its own delayed callbacks only."""
import unittest
import customtkinter as ctk
from retro_beaten.ui.managed_window import ManagedToplevel


class WindowLifecycleTests(unittest.TestCase):
    def test_rapid_close_cancels_child_timers_but_keeps_parent_timer(self):
        root = ctk.CTk()
        root.withdraw()
        try:
            parent_timer = root.after(10000, lambda: None)
            for _ in range(20):
                child = ManagedToplevel(root)
                child.withdraw()
                child.resizable(False, False)
                child.after(10000, self.fail, 'Callback survived window destruction')
                owned = set(child._owned_timers)
                self.assertTrue(owned)
                child.destroy()
                remaining = set(root.tk.call('after', 'info'))
                self.assertFalse(remaining & owned)
                self.assertIn(parent_timer, remaining)
            root.update()
        finally:
            for timer in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', timer)
            root.destroy()
