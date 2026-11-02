"""Window-local visual regression; synthetic covers, no collection/database access."""
import json
import tempfile
import time
from pathlib import Path
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageGrab, ImageColor
from retro_beaten.ui.library_view import create_library_area, render_library
from retro_beaten.ui.theme import apply_theme


def main():
    apply_theme()
    output = Path('build/scroll-visual')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = ctk.CTk()
        root.title('Retro Beaten - Synthetic scroll regression')
        root.geometry('1100x780+40+40')
        area = create_library_area(root)
        games = []
        for platform, count in [('PC', 60), ('PS1', 14), ('PS2', 3), ('PSP', 7)]:
            for i in range(count):
                cover = Path(folder) / f'{platform}-{i}.png'
                im = Image.new('RGB', (300, 400), '#254767')
                draw = ImageDraw.Draw(im)
                draw.rectangle((12, 12, 287, 387), outline='#F8FAFC', width=6)
                for y in range(60, 360, 30):
                    draw.rectangle((20, y, 280, y+10), fill=('#E7B84B' if i % 2 else '#67E8F9'))
                draw.text((24, 25), f'{platform} / {i:02}', fill='white', font_size=24)
                im.save(cover)
                games.append(dict(id=len(games), name=f'{platform} Game {i:02}', platform=platform,
                                  status='beaten', favorite=bool(i % 3), cover_path=cover))
        render_library(area, games, lambda *a: None, lambda *a: None,
                       preferences=dict(cover_size='Small', sort_order='Name A-Z', sections={}),
                       incremental=True)
        errors = []
        root.report_callback_exception = lambda *a: errors.append(str(a[1]))
        def capture(name):
            # Capture this test's HWND, never the whole desktop.
            shot = ImageGrab.grab(window=int(root.frame(), 0)).convert("RGB")
            shot.save(output / f'{name}.png')
            surface = area._shelf_viewport.surface
            ox, oy = surface.winfo_rootx()-root.winfo_rootx(), surface.winfo_rooty()-root.winfo_rooty()
            for _, section in area._shelf_cache.values():
                for _, card in section._cards.values():
                    x, y, w, h = card.bounds
                    expected = ImageColor.getrgb(surface.itemcget(card.border, "fill"))
                    for px, py in ((x+1, y+h*.3), (x+1, y+h*.7), (x+w-2, y+h*.5), (x+w*.5, y+1)):
                        if 2 <= px < surface.winfo_width()-2 and 2 <= py < surface.winfo_height()-2:
                            point = (round(ox+px), round(oy+py))
                            if shot.getpixel(point) != expected:
                                errors.append(f"{name}: broken cover border at {point}")
        def finish():
            capture('settled')
            print(json.dumps(dict(errors=errors, output=str(output.resolve()))), flush=True)
            root.quit()
        def step(index=0):
            # Programmatic scrolling reproduces the scrollbar's canvas path.
            area._parent_canvas.yview_moveto(.58 + index*.005)
            if index in (8, 22, 38):
                root.after(12, capture, f'moving-{index}')
            if index < 45:
                root.after(24, step, index+1)
            else:
                root.after(600, finish)
        root.after(1800, step)
        root.after(15000, root.quit)
        root.mainloop()
        for callback in root.tk.call('after', 'info'):
            root.tk.call('after', 'cancel', callback)
        root.destroy()
        if errors:
            raise SystemExit(1)

if __name__ == '__main__':
    main()
