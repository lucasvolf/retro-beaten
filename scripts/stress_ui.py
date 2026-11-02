"""Synthetic UI stress test. Uses temporary images; never opens personal data."""
import argparse
import json
import tempfile
import time
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from retro_beaten.ui.library_view import create_library_area, render_library, update_favorite_display


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--games', type=int, default=200)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--unique-covers', type=int, default=40)
    args = parser.parse_args()
    if args.games < 1 or args.unique_covers < 1:
        parser.error("games and unique-covers must be positive")
    import faulthandler
    if args.trace:
        faulthandler.dump_traceback_later(30, repeat=True)
    with tempfile.TemporaryDirectory() as folder:
        root = ctk.CTk()
        root.geometry('1200x800')
        root.attributes('-alpha', 0)
        errors, results, ticks = [], {}, []
        root.report_callback_exception = lambda *error: errors.append(str(error[1]))
        area = create_library_area(root)
        covers = []
        for i in range(min(args.games, args.unique_covers)):
            path = Path(folder) / f'{i}.jpg'
            Image.new('RGB', (600, 800), ((i*6) % 256, 70, 90)).save(path)
            covers.append(path)
        games = [dict(id=i, name=f'Game {i:04}', platform='PC', status='beaten',
                      cover_path=covers[i % len(covers)], favorite=False) for i in range(args.games)]
        prefs = dict(cover_size='Medium', sort_order='Name A-Z', sections={})
        def heartbeat():
            ticks.append(time.perf_counter())
            root.after(10, heartbeat)
        def render(query=''):
            render_library(area, games, lambda *a: None, lambda *a: None,
                           query=query, preferences=prefs, incremental=True)
        def measure(name, action):
            ticks.clear()
            started = time.perf_counter()
            action()
            deadline = started + 60
            settled = time.perf_counter() + .4
            def check():
                nonlocal settled
                running = any(s._rendering for _, s in getattr(area, '_shelf_cache', {}).values())
                if running:
                    settled = time.perf_counter() + .4
                if time.perf_counter() >= deadline or (not running and time.perf_counter() >= settled):
                    root.quit()
                else:
                    root.after(20, check)
            root.after(20, check)
            root.mainloop()
            points = [started, *ticks, time.perf_counter()]
            results[name] = dict(seconds=round(points[-1]-started, 3),
                                max_gap_ms=round(max(b-a for a,b in zip(points,points[1:]))*1000, 1),
                                timed_out=time.perf_counter() >= deadline,
                                active_cards=sum(len(s._cards) for _, s in getattr(area, "_shelf_cache", {}).values()))
            print(name, results[name], flush=True)
        root.update()
        heartbeat()
        measure('load', render)
        def favorite():
            for game in games[:100]:
                game['favorite'] = True
                update_favorite_display(area, game)
        measure('100_favorites', favorite)
        prefs['sort_order'] = 'Name Z-A'
        measure('sort', render)
        measure('resize', lambda: root.geometry('980x650'))
        prefs['cover_size'] = 'Small'
        measure('size', render)
        def search():
            for query in ('Game 0', 'Game 00', 'absent', 'Game 001', ''):
                render(query)
        measure('rapid_search', search)
        measure('scroll_bottom', lambda: area._parent_canvas.yview_moveto(1))
        if 0 not in area._shelf_cache["beaten:PC"][1]._cards:
            errors.append("The last sorted record was not rendered at the bottom")
            shelf = area._shelf_cache["beaten:PC"][1]._virtual_shelf
            print("Bottom geometry:", dict(panel_height=shelf.panel.winfo_height(),
                  desired_height=shelf.height, panel_width=shelf.panel.winfo_width(),
                  section_y=shelf.section.winfo_y(), panel_y=shelf.panel.winfo_y(),
                  scroll_y=area._parent_canvas.canvasy(0), scrollregion=area._parent_canvas.cget("scrollregion"),
                  view_key=shelf.view_key), flush=True)
        measure('scroll_top', lambda: area._parent_canvas.yview_moveto(0))
        if args.games - 1 not in area._shelf_cache["beaten:PC"][1]._cards:
            errors.append("The first sorted record was not rendered at the top")
        if args.games > 100 and any(r["active_cards"] > 100 for r in results.values()):
            errors.append("Too many active cover widgets for this viewport")
        faulthandler.cancel_dump_traceback_later()
        print(json.dumps(dict(games=args.games, results=results, errors=errors), indent=2))
        for callback in root.tk.call('after', 'info'):
            root.tk.call('after', 'cancel', callback)
        root.destroy()
        if errors or any(r['timed_out'] for r in results.values()):
            raise SystemExit(1)

if __name__ == '__main__':
    main()
