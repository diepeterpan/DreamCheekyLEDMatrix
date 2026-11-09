"""
Font definitions and loader for Dream Cheeky 21x7 Matrix (.dlf format).
Supports all legacy dcled-master fonts:
- default (5x7 standard X11 font by Jeff Jahr)
- small (4x7 compact font by Stefan Misch)
- sga (Standard Galactic Alphabet by Tom Hall / Stefan Misch)
- small_inv (Very small inverted font by Stefan Misch)

Supports both:
- Fixed width spacing (standard grid cells)
- Proportional width spacing (tight trimming of empty columns, packing more characters into 21 cols)
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("dcled.font")

FONTY = 7

class DCLEDFont:
    def __init__(self, name: str, description: str, author: str, width: int, height: int, data: List[List[int]]):
        self.name = name
        self.description = description
        self.author = author
        self.dispwidth = width
        self.dispheight = height
        self.data = data  # 256 entries, each list of 7 ints (byte rows)

    def get_glyph(self, char: str) -> List[int]:
        code = ord(char) if len(char) == 1 else 32
        if code < 0 or code > 255:
            code = ord('?')
        return self.data[code]

    def get_glyph_columns(self, char: str, proportional: bool = True) -> List[List[int]]:
        """
        Returns the character as a list of vertical columns: [[y0..y6], [y0..y6], ...].
        If proportional is True:
          - Trims empty outer columns to tighten spacing (e.g. '.', '!', '1', 'I' become 1-3 cols).
          - ' ' (space) renders as 2 columns of blanks.
        If proportional is False:
          - Exactly self.dispwidth columns are returned.
        """
        glyph = self.get_glyph(char)

        if not proportional:
            cols = []
            for cx in range(self.dispwidth):
                col_bits = [(glyph[y] >> cx) & 1 for y in range(FONTY)]
                cols.append(col_bits)
            return cols

        # Proportional calculation
        if char == " ":
            space_width = max(2, self.dispwidth // 2)
            return [[0] * FONTY for _ in range(space_width)]

        # Find columns that have any lit pixels
        active_cols = []
        for cx in range(self.dispwidth):
            if any((glyph[y] & (1 << cx)) != 0 for y in range(FONTY)):
                active_cols.append(cx)

        if not active_cols:
            # Blank character fallback
            return [[0] * FONTY for _ in range(2)]

        min_col = min(active_cols)
        max_col = max(active_cols)

        cols = []
        for cx in range(min_col, max_col + 1):
            col_bits = [(glyph[y] >> cx) & 1 for y in range(FONTY)]
            cols.append(col_bits)
        return cols

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "width": self.dispwidth,
            "height": self.dispheight
        }


def parse_dlf_file(filepath: Path) -> Optional[DCLEDFont]:
    """Parses a version 0 .dlf (dcled font) file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        meta = {}
        data_rows = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if ":" in line_str and not line_str[0:2].isalnum():
                parts = line_str.split(":", 1)
                meta[parts[0].strip().lower()] = parts[1].strip()
            elif line_str.startswith("DcledFontVersion:") or line_str.startswith("Name:") or \
                 line_str.startswith("Description:") or line_str.startswith("Author:") or \
                 line_str.startswith("Size:"):
                parts = line_str.split(":", 1)
                meta[parts[0].strip().lower()] = parts[1].strip()
            else:
                tokens = line_str.split()
                if len(tokens) >= 9:
                    bytes_data = [int(h, 16) for h in tokens[2:9]]
                    data_rows.append(bytes_data)

        name = meta.get("name", filepath.stem)
        desc = meta.get("description", "DCLED Font")
        author = meta.get("author", "Unknown")
        width = 5
        height = 7
        if "size" in meta:
            size_parts = meta["size"].lower().split("x")
            if len(size_parts) == 2:
                try:
                    width = int(size_parts[0].strip())
                    height = int(size_parts[1].strip())
                except ValueError:
                    pass

        if len(data_rows) == 256:
            return DCLEDFont(name, desc, author, width, height, data_rows)
        else:
            logger.warning(f"Font file {filepath} had {len(data_rows)} glyphs instead of 256.")
            return None
    except Exception as e:
        logger.error(f"Error parsing font file {filepath}: {e}")
        return None


class FontManager:
    _instance = None

    def __init__(self, fonts_dir: Optional[Path] = None):
        if fonts_dir is None:
            base = Path(__file__).resolve().parent.parent
            fonts_dir = base / "fonts"
        self.fonts_dir = fonts_dir
        self.fonts: Dict[str, DCLEDFont] = {}
        self.load_all_fonts()

    @classmethod
    def get_instance(cls) -> "FontManager":
        if cls._instance is None:
            cls._instance = FontManager()
        return cls._instance

    def load_all_fonts(self):
        self.fonts.clear()
        if not self.fonts_dir.exists():
            logger.warning(f"Fonts directory {self.fonts_dir} does not exist.")
            return

        for fpath in self.fonts_dir.glob("*.dlf"):
            font = parse_dlf_file(fpath)
            if font:
                self.fonts[font.name] = font
                logger.info(f"Loaded DCLED font '{font.name}' ({font.dispwidth}x{font.dispheight}) - {font.description}")

        # Ensure fallback 'default'
        if "default" not in self.fonts and len(self.fonts) > 0:
            first_key = next(iter(self.fonts))
            self.fonts["default"] = self.fonts[first_key]

    def get_font(self, name: str = "default") -> DCLEDFont:
        if name in self.fonts:
            return self.fonts[name]
        if "default" in self.fonts:
            return self.fonts["default"]
        return DCLEDFont("empty", "Empty fallback", "None", 5, 7, [[0] * 7 for _ in range(256)])

    def list_fonts(self) -> List[Dict[str, Any]]:
        return [font.to_dict() for font in self.fonts.values()]


# Singleton helpers
_font_mgr = FontManager.get_instance()

def get_font_manager() -> FontManager:
    return _font_mgr

def get_glyph(char: str, font_name: str = "default") -> List[int]:
    return _font_mgr.get_font(font_name).get_glyph(char)
