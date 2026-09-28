"""Crop the AI-generated Aesop image: remove the title bar at the top.
Input:  slides/figures/aesop_wolf.png
Output: slides/figures/aesop_wolf.png  (overwritten in place)
Run once after dropping the source image into slides/figures/.
"""
from PIL import Image
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "slides", "figures", "aesop_wolf.png")

img = Image.open(PATH)
w, h = img.size
# Title bar occupies roughly the top 13 % of the image
crop_top = int(h * 0.13)
cropped = img.crop((0, crop_top, w, h))
cropped.save(PATH)
print(f"Cropped {PATH}  ({w}x{h} → {w}x{h - crop_top})")
