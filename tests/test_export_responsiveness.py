"""Export isolation, cancellation, and atomic publication."""

import tempfile
import time
import unittest
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from retro_beaten.services.export_job import ExportJob
from retro_beaten.services.shelf_tools import export_shelf, ExportCancelled


class ExportResponsivenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        cover = self.folder / "cover.jpg"
        Image.effect_noise((600, 800), 60).convert("RGB").save(cover)
        self.games = [dict(id=i, name=f"Game {i}", platform="PC", status="beaten", cover_path=cover)
                      for i in range(80)]

    def test_process_export_keeps_tk_events_running(self):
        root = ctk.CTk()
        root.withdraw()
        target = self.folder / "shelf.png"
        job = ExportJob(self.games, target, {}, "Beaten only")
        ticks, packets = [], []
        deadline = time.monotonic() + 20
        try:
            def pulse():
                ticks.append(time.monotonic())
                packets.extend(job.messages())
                if any(kind != "progress" for kind, _ in packets) or time.monotonic() > deadline:
                    root.quit()
                else:
                    root.after(10, pulse)
            root.after(10, pulse)
            root.mainloop()
            self.assertIn("success", [kind for kind, _ in packets])
            self.assertGreater(len(ticks), 5)
            self.assertIn("progress", [kind for kind, _ in packets])
            with Image.open(target) as image:
                self.assertEqual(image.width, 1600)
                image.verify()
        finally:
            job.close()
            root.destroy()

    def test_cancel_preserves_destination_and_removes_temporary(self):
        target = self.folder / "shelf.png"
        target.write_bytes(b"existing export")
        job = ExportJob(self.games, target, {}, "Beaten only")
        job.cancel()
        packets = []
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                packets.extend(job.messages())
                if any(kind != "progress" for kind, _ in packets):
                    break
                time.sleep(0.02)
            self.assertIn("cancelled", [kind for kind, _ in packets])
            self.assertEqual(target.read_bytes(), b"existing export")
            self.assertFalse(job.temporary.exists())
        finally:
            job.close()

    def test_service_cancel_during_render_does_not_publish(self):
        target = self.folder / "shelf.png"
        cancelled = False
        def progress(done, total, text):
            nonlocal cancelled
            if done >= 3:
                cancelled = True
        with self.assertRaises(ExportCancelled):
            export_shelf(self.games, target, {}, progress=progress, cancelled=lambda: cancelled)
        self.assertFalse(target.exists())
