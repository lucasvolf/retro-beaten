"""Optional packaged-app test with a temporary collection and no network access."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import traceback

from PIL import Image

from retro_beaten.app import RetroBeatenApp
from retro_beaten.paths import get_data_dir
from retro_beaten.services.export_job import ExportJob
from retro_beaten.services.backup import create_backup, restore_backup
from retro_beaten.services.collection import register_manual_game
from retro_beaten.storage.database import initialize_database, load_saved_games


def run_self_test(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "data_dir": str(get_data_dir())}
    app = None
    export_job = None
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
            app.window.attributes("-alpha", 0)
            callback_errors = []

            def failure(kind, error, trace):
                callback_errors.append("".join(traceback.format_exception(kind, error, trace)))
                app.window.quit()

            def show_details():
                assert app.drop_handler is not None, "Native file-drop support was not bundled."
                app.select_shelf("beaten")
                app.sidebar.toggle()
                app.change_favorite(app.games[0], True)
                app.toggle_exhibition()
                app.exit_exhibition()
                app.open_details(app.games[0])
                app.window.after(300, finish)

            def finish():
                assert app.details_window.cover_display is not None
                assert app.details_window.name_label.cget("text") == "Executable test"
                assert len(load_saved_games(database, project)) == 1
                nonlocal export_job
                export_job = ExportJob(app.games, project / "shelf.png", app.preferences, "Entire collection")
                app.window.after(20, check_export)

            def check_export():
                for kind, value in export_job.messages():
                    if kind == "error" or kind == "cancelled":
                        raise RuntimeError(value)
                    if kind == "success":
                        with Image.open(project / "shelf.png") as exported:
                            assert exported.width == 1600
                            exported.verify()
                        assert load_saved_games(database, project)[0]["favorite"]
                        report["checks"] = ["backup", "restore", "sidebar", "favorites",
                                            "exhibition", "details", "native_file_drop", "process_png_export"]
                        report["ok"] = True
                        app.window.quit()
                        return
                app.window.after(20, check_export)

            app.window.report_callback_exception = failure
            app.window.after(500, show_details)
            app.window.after(45000, app.window.quit)
            app.run()
            if callback_errors:
                raise RuntimeError("\n".join(callback_errors))
            if not report["ok"]:
                raise RuntimeError("The interface test did not finish.")
    except Exception:
        report["ok"] = False
        report["error"] = traceback.format_exc()
    finally:
        if export_job is not None:
            export_job.close()
        if app is not None:
            for callback in app.window.tk.call("after", "info"):
                app.window.tk.call("after", "cancel", callback)
            app.window.destroy()
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise SystemExit(1)
