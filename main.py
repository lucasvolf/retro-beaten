"""Retro Beaten entry point."""

from retro_beaten.app import RetroBeatenApp
from retro_beaten.error_reporting import report_exception
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from retro_beaten.diagnostics import run_self_test
        return run_self_test(sys.argv[2])
    try:
        app = RetroBeatenApp()
        app.window.report_callback_exception = report_exception
        app.run()
    except Exception:
        report_exception(*sys.exc_info())
        raise SystemExit(1)


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    main()
