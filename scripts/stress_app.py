"""End-to-end stress test with temporary data and no online services."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import ctypes
import gc
import faulthandler
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import customtkinter as ctk
from PIL import Image
from retro_beaten.app import RetroBeatenApp
from retro_beaten.storage.database import initialize_database, load_saved_games
from retro_beaten.services.backup import create_backup, restore_backup
from retro_beaten.services.export_job import ExportJob


def private_memory_mb():
    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged',
            'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(kernel.GetCurrentProcess()), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return round(counters.private / 1024**2, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--games', type=int, default=1000)
    parser.add_argument('--cycles', type=int, default=15)
    parser.add_argument('--report', default='build/release-app-stress.json')
    args = parser.parse_args()
    if args.games < 20 or args.cycles < 1:
        parser.error('Use at least 20 games and one navigation cycle.')
    if args.trace:
        faulthandler.dump_traceback_later(60, repeat=True)
    results, errors, ticks = {}, [], []
    report = dict(games=args.games, cycles=args.cycles, results=results, errors=errors)
    root = None
    try:
        with TemporaryDirectory(prefix='retro-beaten-stress-') as folder:
            project = Path(folder)
            images = project / 'assets/images'
            images.mkdir(parents=True)
            source = images / 'source.jpg'
            Image.effect_noise((300, 400), 80).convert('RGB').save(source)
            payload = source.read_bytes()
            database = project / 'data/retro_beaten.db'
            initialize_database(database)
            records = []
            for i in range(args.games):
                cover = images / f'{i}.jpg'
                cover.write_bytes(payload)
                status = 'playing' if i % 10 == 0 else 'wishlist' if i % 10 == 9 else 'beaten'
                records.append((f'Game {i:04}', 'PS1' if i % 5 == 0 else 'PC',
                                cover.relative_to(project).as_posix(), status))
            with closing(sqlite3.connect(database)) as connection:
                connection.executemany('INSERT INTO games(name,platform,cover_path,status) VALUES(?,?,?,?)', records)
                connection.commit()
            root = ctk.CTk()
            root.geometry('1280x850')
            root.attributes('-alpha', 0)
            root.report_callback_exception = lambda *exc: errors.append(str(exc[1]))
            def heartbeat():
                ticks.append(time.perf_counter())
                root.after(10, heartbeat)
            heartbeat()
            started = time.perf_counter()
            with patch('retro_beaten.app.create_window', return_value=root):
                app = RetroBeatenApp(project)
            def measure(name, action, ready=lambda: True, start=None):
                ticks.clear()
                begin = start if start is not None else time.perf_counter()
                action()
                settled = time.perf_counter() + .5
                def check():
                    nonlocal settled
                    now = time.perf_counter()
                    running = any(s._rendering for _, s in app.library_area._shelf_cache.values())
                    if running or not ready():
                        settled = now + .5
                    if now - begin > 90 or (not running and now >= settled):
                        root.quit()
                    else:
                        root.after(20, check)
                root.after(20, check)
                root.mainloop()
                points = [begin, *ticks, time.perf_counter()]
                result = dict(seconds=round(points[-1]-begin, 3),
                              max_gap_ms=round(max(b-a for a,b in zip(points, points[1:]))*1000, 1),
                              active_cards=sum(len(s._cards) for _, s in app.library_area._shelf_cache.values()))
                results[name] = result
                print(name, result, flush=True)
                if errors or points[-1]-begin > 90:
                    raise RuntimeError(f'{name}: callback error or timeout: {errors}')
            def resources():
                gc.collect()
                return dict(private_mb=private_memory_mb(),
                            images=len(root.tk.call('image', 'names')),
                            commands=len(root.tk.call('info', 'commands')),
                            timers=len(root.tk.call('after', 'info')))
            measure('startup', lambda: None, start=started)
            measure('beaten', lambda: app.select_shelf('beaten'))
            measure('favorite', lambda: app.change_favorite(app.games[1], True))
            measure('search', lambda: app.local_search.query.set('Game 00'))
            measure('clear_search', lambda: app.local_search.query.set(''))
            measure('sidebar', app.sidebar.toggle)
            measure('large_covers', lambda: app.change_view('cover_size', 'Large'))
            measure('small_covers', lambda: app.change_view('cover_size', 'Small'))
            measure('scroll_bottom', lambda: app.library_area._parent_canvas.yview_moveto(1))
            measure('scroll_top', lambda: app.library_area._parent_canvas.yview_moveto(0))
            measure('exhibition', app.toggle_exhibition)
            measure('exit_exhibition', app.exit_exhibition)
            for i in range(3):
                measure(f'warm_playing_{i}', lambda: app.select_shelf('playing'))
                measure(f'warm_beaten_{i}', lambda: app.select_shelf('beaten'))
            report['resources_before'] = resources()
            for i in range(args.cycles):
                measure(f'playing_{i}', lambda: app.select_shelf('playing'))
                measure(f'beaten_{i}', lambda: app.select_shelf('beaten'))
            report['resources_after'] = resources()
            before, after = report['resources_before'], report['resources_after']
            for key, tolerance in (('private_mb',40), ('images',10), ('commands',40)):
                if after[key] - before[key] > tolerance:
                    errors.append(f'Resource growth in {key}: {before[key]} -> {after[key]}')
            def dialogs():
                for _ in range(10):
                    app.open_details(app.games[1])
                    app.details_window.destroy()
            measure('close_dialogs', dialogs)
            destination = project / 'shelf.png'
            job = ExportJob(app.games, destination, app.preferences, 'Entire collection')
            terminal = []
            def export_done():
                terminal.extend((kind, value) for kind,value in job.messages() if kind != 'progress')
                return bool(terminal)
            try:
                measure('export', lambda: None, export_done)
                assert terminal and terminal[0][0] == 'success', terminal
                with Image.open(destination) as exported:
                    exported.verify()
            finally:
                job.close()
            with ThreadPoolExecutor(max_workers=1) as worker:
                archive = project / 'backup.zip'
                future = worker.submit(create_backup, database, project, archive)
                measure('backup', lambda: None, future.done)
                future.result()
                future = worker.submit(restore_backup, database, project, archive)
                measure('restore', lambda: None, future.done)
                future.result()
            measure('reload_restored', app.reload_collection)
            restored = load_saved_games(database, project)
            assert len(restored) == args.games and all(g['cover_path'].is_file() for g in restored)
            assert restored[1]['favorite']
    except Exception as error:
        errors.append(f'{type(error).__name__}: {error}')
    finally:
        if root is not None:
            for callback in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', callback)
            root.destroy()
        faulthandler.cancel_dump_traceback_later()
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
