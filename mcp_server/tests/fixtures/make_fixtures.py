"""Test görüntülerini yeniden üretir. Çıktılar repoda duruyor; bu betik sadece
nasıl üretildiklerini belgelemek ve gerekirse yeniden üretmek için.

    venv\Scripts\python.exe mcp_server\tests\fixtures\make_fixtures.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE.parents[2] / "Fonts" / "Grift-Bold.ttf"


def make_text_image() -> None:
    img = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), 56)
    draw.text((40, 40), "AIRON MCP TEST", fill="black", font=font)
    draw.text((40, 140), "Kahve 42 TL", fill="black", font=font)
    img.save(HERE / "text_sample.png")


def make_blank_image() -> None:
    Image.new("RGB", (400, 200), "white").save(HERE / "blank.png")


if __name__ == "__main__":
    make_text_image()
    make_blank_image()
