"""
Effects and Rendering Pipeline for 21x7 Dream Cheeky Matrix.
Supports:
- Proportional vs Fixed spacing rendering to maximize character capacity in 21 cols
- Font rendering with selectable dcled-master fonts (default, small, sga, small_inv)
- Static text (centered or left-aligned)
- Scrolling in all directions: West (Left), East (Right), North (Up), South (Down)
- Legacy animations: Fire, Spiral, TV Warmup Static, Squiggle, Clock (12h/24h), Binary BCD Clock
- Tachometer / Bar graphs
"""

import math
import random
import time
from typing import List, Generator, Tuple
from backend.font import get_font_manager

LEDSX = 21
LEDSY = 7

def create_blank_matrix() -> List[List[int]]:
    return [[0 for _ in range(LEDSY)] for _ in range(LEDSX)]

def render_string_to_buffer(text: str, font_name: str = "default", spacing_mode: str = "proportional") -> List[List[int]]:
    """
    Renders text into a continuous pixel column buffer.
    spacing_mode: 'proportional' (trims whitespace around narrow characters) or 'fixed' (monospaced grid).
    """
    if not text:
        return create_blank_matrix()

    font = get_font_manager().get_font(font_name)
    is_proportional = (spacing_mode.lower() == "proportional")

    columns: List[List[int]] = []

    for idx, char in enumerate(text):
        char_cols = font.get_glyph_columns(char, proportional=is_proportional)
        for col in char_cols:
            columns.append(col)
        # Add 1-column spacing between characters (unless last character)
        if idx < len(text) - 1:
            columns.append([0] * LEDSY)

    # Ensure buffer is at least LEDSX wide
    while len(columns) < LEDSX:
        columns.append([0] * LEDSY)

    return columns

def render_static_text(text: str, align: str = "center", font_name: str = "default", spacing_mode: str = "proportional") -> List[List[int]]:
    """
    Renders text directly into a 21x7 matrix without scrolling.
    If text fits within 21 columns, it will be centered or left-aligned.
    """
    matrix = create_blank_matrix()
    if not text:
        return matrix

    buffer = render_string_to_buffer(text, font_name=font_name, spacing_mode=spacing_mode)
    text_width = len(buffer)
    # Trim trailing padding blanks if buffer was padded
    # Find actual occupied width
    occupied_width = 0
    for idx in range(len(buffer) - 1, -1, -1):
        if any(buffer[idx][y] != 0 for y in range(LEDSY)):
            occupied_width = idx + 1
            break
    if occupied_width == 0:
        return matrix

    if align == "center" and occupied_width <= LEDSX:
        start_x = (LEDSX - occupied_width) // 2
    else:
        start_x = 0

    for x in range(occupied_width):
        dest_x = start_x + x
        if 0 <= dest_x < LEDSX:
            for y in range(LEDSY):
                matrix[dest_x][y] = buffer[x][y]

    return matrix

class EffectsEngine:
    def __init__(self):
        # Fire state
        self.fire_grid = create_blank_matrix()
        # Spiral state
        self.spiral_step = 0
        self.spiral_state = 1
        # Tachometer value
        self.tach_val = 50

    def flash_frames(self, text: str, font_name: str = "default", spacing_mode: str = "proportional", blink_count: int = 4) -> Generator[List[List[int]], None, None]:
        """Alternates between rendered static text and a blank matrix to create a flashing effect."""
        text_frame = render_static_text(text, align="center", font_name=font_name, spacing_mode=spacing_mode)
        blank_frame = create_blank_matrix()
        for _ in range(blink_count):
            yield text_frame
            yield blank_frame

    def scroll_west_frames(self, text: str, font_name: str = "default", spacing_mode: str = "proportional") -> Generator[List[List[int]], None, None]:
        """Scroll from right to left (standard reading)."""
        buffer = render_string_to_buffer(text, font_name=font_name, spacing_mode=spacing_mode)
        buf_width = len(buffer)

        for offset in range(-LEDSX, buf_width + 1):
            frame = create_blank_matrix()
            for x in range(LEDSX):
                src_x = offset + x
                if 0 <= src_x < buf_width:
                    for y in range(LEDSY):
                        frame[x][y] = buffer[src_x][y]
            yield frame

    def scroll_east_frames(self, text: str, font_name: str = "default", spacing_mode: str = "proportional") -> Generator[List[List[int]], None, None]:
        """Scroll from left to right."""
        buffer = render_string_to_buffer(text, font_name=font_name, spacing_mode=spacing_mode)
        buf_width = len(buffer)

        for offset in range(buf_width + LEDSX, -LEDSX - 1, -1):
            frame = create_blank_matrix()
            for x in range(LEDSX):
                src_x = offset + x
                if 0 <= src_x < buf_width:
                    for y in range(LEDSY):
                        frame[x][y] = buffer[src_x][y]
            yield frame

    def scroll_north_frames(self, text: str, font_name: str = "default", spacing_mode: str = "proportional") -> Generator[List[List[int]], None, None]:
        """Scroll vertically upwards."""
        static_frame = render_static_text(text, align="center", font_name=font_name, spacing_mode=spacing_mode)
        for y_shift in range(-LEDSY, LEDSY + 1):
            frame = create_blank_matrix()
            for x in range(LEDSX):
                for y in range(LEDSY):
                    src_y = y + y_shift
                    if 0 <= src_y < LEDSY:
                        frame[x][y] = static_frame[x][src_y]
            yield frame

    def scroll_south_frames(self, text: str, font_name: str = "default", spacing_mode: str = "proportional") -> Generator[List[List[int]], None, None]:
        """Scroll vertically downwards."""
        static_frame = render_static_text(text, align="center", font_name=font_name, spacing_mode=spacing_mode)
        for y_shift in range(LEDSY, -LEDSY - 1, -1):
            frame = create_blank_matrix()
            for x in range(LEDSX):
                for y in range(LEDSY):
                    src_y = y + y_shift
                    if 0 <= src_y < LEDSY:
                        frame[x][y] = static_frame[x][src_y]
            yield frame

    def render_fire_step(self) -> List[List[int]]:
        """Simulate a glowing flickering fireplace (matches dcled.c)."""
        new_grid = create_blank_matrix()
        # Scroll up
        for x in range(LEDSX):
            for y in range(LEDSY - 1):
                new_grid[x][y] = self.fire_grid[x][y + 1]

        # Extinguish some embers randomly
        for x in range(LEDSX):
            for y in range(LEDSY):
                burnrate = random.random()
                if (x / LEDSX) < (burnrate * burnrate):
                    new_grid[x][y] = 0

        # Feed new fire line at bottom
        fire_width = random.randint(10, LEDSX)
        for x in range(fire_width):
            new_grid[x][LEDSY - 1] = 1 if random.random() > 0.3 else 0

        self.fire_grid = new_grid
        return [row[:] for row in new_grid]

    def render_static_warmup(self, frame_num: int, total_frames: int = 30) -> List[List[int]]:
        """TV Warmup effect with white noise settling into clear screen."""
        frame = create_blank_matrix()
        decay = max(0.0, 1.0 - (frame_num / total_frames))
        for x in range(LEDSX):
            for y in range(LEDSY):
                frame[x][y] = 1 if random.random() < decay else 0
        return frame

    def render_squiggle_step(self, frame_num: int) -> List[List[int]]:
        """Animated random sine/squiggle curve running across matrix."""
        frame = create_blank_matrix()
        for x in range(LEDSX):
            y = int(3 + 2.5 * math.sin((x + frame_num * 0.5) * 0.4))
            if 0 <= y < LEDSY:
                frame[x][y] = 1
        return frame

    def render_clock(self, mode_24h: bool = True, font_name: str = "default", spacing_mode: str = "proportional") -> List[List[int]]:
        """Renders HH:MM with blinking colon."""
        now = time.localtime()
        fmt = "%H:%M" if mode_24h else "%I:%M"
        time_str = time.strftime(fmt, now)
        blink = (int(time.time()) % 2) == 0
        display_str = time_str if blink else time_str.replace(":", " ")
        return render_static_text(display_str, align="center", font_name=font_name, spacing_mode=spacing_mode)

    def render_bcd_clock(self) -> List[List[int]]:
        """Binary Coded Decimal clock (hours, minutes, seconds as vertical binary bars)."""
        now = time.localtime()
        digits = [
            now.tm_hour // 10, now.tm_hour % 10,
            now.tm_min // 10, now.tm_min % 10,
            now.tm_sec // 10, now.tm_sec % 10
        ]
        matrix = create_blank_matrix()
        cols = [2, 5, 9, 12, 16, 19]

        for idx, d in enumerate(digits):
            col = cols[idx]
            for bit in range(4):
                row = LEDSY - 1 - bit
                if (d & (1 << bit)) != 0:
                    matrix[col][row] = 1
        return matrix

    def render_tach(self, percent: int, label: str = "") -> List[List[int]]:
        """Horizontal percentage load tachometer."""
        matrix = create_blank_matrix()
        percent = max(0, min(100, percent))
        filled_cols = round((percent / 100.0) * LEDSX)

        for x in range(filled_cols):
            for y in range(LEDSY):
                matrix[x][y] = 1
        return matrix
