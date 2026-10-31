"""Report unexpected errors even when the executable has no console."""

from datetime import datetime
from tkinter import messagebox
import traceback

from retro_beaten.paths import get_data_dir


def report_exception(kind, error, trace):
    path = get_data_dir() / "logs/errors.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(f"\n{datetime.now().isoformat()}\n")
            traceback.print_exception(kind, error, trace, file=output)
        detail = f"Details were saved to:\n{path}"
    except OSError:
        detail = "Could not save the diagnostic log. Check the data folder permissions."
    messagebox.showerror("Retro Beaten", f"An unexpected error occurred.\n\n{detail}")
