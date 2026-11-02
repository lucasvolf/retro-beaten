"""Toplevel windows that cancel their own timers before Tcl commands disappear."""
import customtkinter as ctk


class ManagedToplevel(ctk.CTkToplevel):
    def __init__(self, *args, **kwargs):
        self._owned_timers = set()
        super().__init__(*args, **kwargs)

    def after(self, ms, func=None, *args):
        if func is None:
            return super().after(ms)
        timer = None
        def invoke():
            self._owned_timers.discard(timer)
            return func(*args)
        timer = super().after(ms, invoke)
        self._owned_timers.add(timer)
        return timer

    def after_cancel(self, timer):
        self._owned_timers.discard(timer)
        return super().after_cancel(timer)

    def destroy(self):
        for timer in tuple(self._owned_timers):
            self.after_cancel(timer)
        super().destroy()
