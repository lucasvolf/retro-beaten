"""Capture only a temporary app window in expanded, rail, and exhibition layouts."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageGrab
from retro_beaten.app import RetroBeatenApp


def main():
    output = Path("build/sidebar-visual")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = ctk.CTk()
        root.geometry("1280x850+40+40")
        root.title("Retro Beaten - Layout verification")
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        with patch("retro_beaten.app.create_window", return_value=root):
            app = RetroBeatenApp(folder)
        covers = sorted(Path("assets/images").glob("*"))
        covers = [p for p in covers if p.suffix.lower() in (".jpg", ".png", ".jpeg")][:20]
        if not covers:
            for i in range(20):
                path = Path(folder)/f"cover-{i}.png"
                image = Image.new("RGB", (300,400), (25+i*5, 30, 55+i*4))
                draw = ImageDraw.Draw(image)
                draw.polygon([(0,400),(300,80),(300,400)],fill=(60+i*5,65,110))
                draw.text((24,30),f"ADVENTURE {i+1}",fill="white",font_size=22)
                image.save(path)
                covers.append(path)
        app.games = [dict(id=i, name=f"Game {i:02}", status="playing" if i<3 else "beaten",
                          platform="PC" if i<12 else "PS1", favorite=i%3==0, cover_path=cover)
                     for i,cover in enumerate(covers)]
        app.preferences["cover_size"] = "Small"
        app.view_controls.size_menu.set("Small")
        app.select_shelf("beaten")
        def capture(name):
            ImageGrab.grab(window=int(root.frame(),0)).save(output/f"{name}.png")
        def collapsed():
            capture("expanded")
            app.sidebar.toggle()
            root.after(800, exhibition)
        def exhibition():
            capture("collapsed")
            app.toggle_exhibition()
            root.after(800, finish)
        def finish():
            capture("exhibition")
            print({"errors":errors,"output":str(output.resolve())},flush=True)
            root.quit()
        root.after(2200,collapsed)
        root.after(15000,root.quit)
        root.mainloop()
        for callback in root.tk.call("after","info"):
            root.tk.call("after","cancel",callback)
        root.destroy()
        if errors: raise SystemExit(1)

if __name__ == "__main__": main()
