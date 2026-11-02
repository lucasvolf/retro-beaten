"""Native file drops, parsed as Tcl lists to preserve spaces in paths."""

from pathlib import Path
from types import SimpleNamespace
from tkinter import messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES, COPY, REFUSE_DROP


def enable_cover_drop(root, on_cover):
    TkinterDnD.require(root)

    def dropped(event):
        paths = root.tk.splitlist(event.data)
        if len(paths) != 1 or Path(paths[0]).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            messagebox.showinfo("Drop a cover", "Drop one PNG, JPEG or WebP image at a time.", parent=root)
            return REFUSE_DROP
        on_cover(Path(paths[0]))
        return COPY

    # CTk's root is a Tk, not a BaseWidget; register the native target directly.
    root.tk.call("tkdnd::drop_target", "register", root._w, (DND_FILES,))
    command = root.register(lambda data: dropped(SimpleNamespace(data=data)))
    root.tk.call("bind", root._w, "<<Drop>>", command + " %D")
    return dropped
