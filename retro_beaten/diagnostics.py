"""Optional packaged-app test with a temporary collection and no network access."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import traceback

from PIL import Image

from retro_beaten.app import RetroBeatenApp
from retro_beaten.paths import get_data_dir
from retro_beaten.services.backup import create_backup, restore_backup
from retro_beaten.services.collection import register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games


def run_self_test(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "data_dir": str(get_data_dir())}
    app = None
    try:
        with TemporaryDirectory(prefix="retro-beaten-self-test-") as folder:
            project = Path(folder)
            database = project / "data/retro_beaten.db"
            initialize_database(database)
            image = project / "cover.png"
            Image.new("RGB", (150, 200), "#E7B84B").save(image)
            register_manual_game(database, project, "Executable test", "PS1", "beaten", image)
            archive = project / "test.zip"
            create_backup(database, project, archive)
            restore_backup(database, project, archive)
            app = RetroBeatenApp(project)
            callback_errors = []

            def failure(kind, error, trace):
                callback_errors.append("".join(traceback.format_exception(kind, error, trace)))
                app.window.quit()

            def show_details():
                app.open_details(app.games[0])
                app.window.after(300, finish)

            def finish():
                assert app.details_window.cover_display is not None
                assert app.details_window.name_label.cget("text") == "Executable test"
                assert len(load_saved_games(database, project)) == 1
                report["ok"] = True
                app.window.quit()

            app.window.report_callback_exception = failure
            app.window.after(500, show_details)
            app.window.after(10000, app.window.quit)
            app.run()
            if callback_errors:
                raise RuntimeError("\n".join(callback_errors))
            if not report["ok"]:
                raise RuntimeError("The interface test did not finish.")
    except Exception:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    finally:
        if app is not None:
            app.window.destroy()
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise SystemExit(1)
