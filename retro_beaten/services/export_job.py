"""Process-isolated PNG rendering; workers never retain Tk widgets."""

import multiprocessing as mp
from pathlib import Path
from queue import Empty
from uuid import uuid4
from retro_beaten.services.shelf_tools import export_shelf, ExportCancelled


def run_export(games, destination, preferences, scope, temporary, results, cancellation):
    try:
        export_shelf(games, destination, preferences, scope,
                     progress=lambda done, total, text: results.put(("progress", (done, total, text))),
                     cancelled=cancellation.is_set, temporary_path=temporary)
    except ExportCancelled:
        results.put(("cancelled", "Export cancelled. The previous file was kept."))
    except Exception as error:
        results.put(("error", f"Could not export: {error}"))
    else:
        results.put(("success", f"Saved: {destination}"))


class ExportJob:
    def __init__(self, games, destination, preferences, scope):
        context = mp.get_context("spawn")
        self.results = context.Queue()
        self.cancellation = context.Event()
        destination = Path(destination)
        self.temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        self.process = context.Process(target=run_export,
            args=(games, str(destination), preferences, scope, str(self.temporary), self.results, self.cancellation),
            daemon=True)
        self.closed = False
        self.process.start()

    def messages(self):
        messages = []
        try:
            while True:
                messages.append(self.results.get_nowait())
        except Empty:
            return messages

    def cancel(self):
        self.cancellation.set()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=0.05)
        self.results.close()
        try:
            self.temporary.unlink(missing_ok=True)
        except OSError:
            pass
