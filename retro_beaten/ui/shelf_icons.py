"""Small original line icons; no external logos or image downloads."""

from functools import lru_cache
from PIL import Image, ImageDraw
import customtkinter as ctk


@lru_cache(maxsize=16)
def icon_pixels(title):
    image = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(image)
    ink = "#969BA5"
    if title == "PC":
        draw.rounded_rectangle((8, 10, 56, 44), radius=4, outline=ink, width=4)
        draw.line((32, 44, 32, 54), fill=ink, width=4)
        draw.line((20, 55, 44, 55), fill=ink, width=4)
    elif "Nintendo" in title and "Switch" not in title:
        for y in (7, 34):
            draw.rounded_rectangle((13, y, 51, y+23), radius=4, outline=ink, width=3)
            draw.rectangle((22, y+5, 42, y+17), outline=ink, width=2)
    elif "Boy" in title or "Portable" in title or "Switch" in title:
        draw.rounded_rectangle((5, 15, 59, 49), radius=9, outline=ink, width=3)
        draw.rectangle((21, 21, 43, 43), outline=ink, width=2)
        draw.line((10, 31, 18, 31), fill=ink, width=2)
        draw.line((14, 27, 14, 35), fill=ink, width=2)
        draw.ellipse((49, 29, 53, 33), fill=ink)
    elif "PlayStation" in title:
        draw.rounded_rectangle((5, 18, 59, 48), radius=12, outline=ink, width=3)
        draw.line((13, 32, 29, 32), fill=ink, width=3)
        draw.line((21, 24, 21, 40), fill=ink, width=3)
        for x,y in ((45,25),(51,32),(39,32),(45,39)):
            draw.ellipse((x-2,y-2,x+2,y+2), fill=ink)
    elif title == "Playing":
        draw.polygon(((21,12),(51,32),(21,52)), outline=ink, width=3)
    else:
        draw.rounded_rectangle((13, 9, 51, 55), radius=4, outline=ink, width=3)
        draw.line((22, 22, 42, 22), fill=ink, width=3)
        draw.line((22, 32, 42, 32), fill=ink, width=3)
        draw.line((22, 42, 36, 42), fill=ink, width=3)
    return image


def shelf_icon(title):
    return ctk.CTkImage(light_image=icon_pixels(title), dark_image=icon_pixels(title), size=(22, 22))
