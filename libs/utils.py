import ctypes
import hashlib
import sys
import logging
import time
from libs.global_data import PlayerNum, global_data
from pathlib import Path
from typing import Optional

import pyray as ray
import raylib as rl
from raylib import (
    SHADER_UNIFORM_FLOAT,
    SHADER_UNIFORM_VEC2,
    SHADER_UNIFORM_VEC4,
)

from libs.texture import TextureWrapper

logger = logging.getLogger(__name__)

def force_dedicated_gpu():
    """Force Windows to use dedicated GPU for this application"""
    if sys.platform == "win32":
        try:
            # NVIDIA Optimus
            nvapi = ctypes.windll.kernel32.LoadLibraryW("nvapi64.dll")
            if nvapi:
                ctypes.windll.kernel32.SetEnvironmentVariableW("SHIM_MCCOMPAT", "0x800000001")
        except Exception as e:
            logger.error(e)

def rounded(num: float) -> int:
    """Round a number to the nearest integer"""
    sign = 1 if (num >= 0) else -1
    num = abs(num)
    result = int(num)
    if (num - result >= 0.5):
        result += 1
    return sign * result

def get_current_ms() -> int:
    """Get the current time in milliseconds"""
    return rounded(time.time() * 1000)

def strip_comments(code: str) -> str:
    """Strip comments from a string of code"""
    result = ''
    index = 0
    for line in code.splitlines():
        comment_index = line.find('//')
        if comment_index == -1:
            result += line
        elif comment_index != 0 and not line[:comment_index].isspace():
            result += line[:comment_index]
        index += 1
    return result

def is_input_key_pressed(keys: list[int], gamepad_buttons: list[int]):
    if global_data.input_locked:
        return False
    for key in keys:
        if rl.IsKeyPressed(key):
            return True

    if rl.IsGamepadAvailable(0):
        for button in gamepad_buttons:
            if rl.IsGamepadButtonPressed(0, button):
                return True

    return False

def is_l_don_pressed(player_num: PlayerNum = PlayerNum.ALL) -> bool:
    """Check if the left don button is pressed"""
    if player_num == PlayerNum.ALL:
        keys = global_data.config["keys_1p"]["left_don"] + global_data.config["keys_2p"]["left_don"]
    elif player_num == PlayerNum.P1:
        keys = global_data.config["keys_1p"]["left_don"]
    elif player_num == PlayerNum.P2:
        keys = global_data.config["keys_2p"]["left_don"]
    else:
        return False
    gamepad_buttons = global_data.config["gamepad"]["left_don"]
    return is_input_key_pressed(keys, gamepad_buttons)

def is_r_don_pressed(player_num: PlayerNum = PlayerNum.ALL) -> bool:
    """Check if the right don button is pressed"""
    if player_num == PlayerNum.ALL:
        keys = global_data.config["keys_1p"]["right_don"] + global_data.config["keys_2p"]["right_don"]
    elif player_num == PlayerNum.P1:
        keys = global_data.config["keys_1p"]["right_don"]
    elif player_num == PlayerNum.P2:
        keys = global_data.config["keys_2p"]["right_don"]
    else:
        return False
    gamepad_buttons = global_data.config["gamepad"]["right_don"]
    return is_input_key_pressed(keys, gamepad_buttons)

def is_l_kat_pressed(player_num: PlayerNum = PlayerNum.ALL) -> bool:
    """Check if the left kat button is pressed"""
    if player_num == PlayerNum.ALL:
        keys = global_data.config["keys_1p"]["left_kat"] + global_data.config["keys_2p"]["left_kat"]
    elif player_num == PlayerNum.P1:
        keys = global_data.config["keys_1p"]["left_kat"]
    elif player_num == PlayerNum.P2:
        keys = global_data.config["keys_2p"]["left_kat"]
    else:
        return False
    gamepad_buttons = global_data.config["gamepad"]["left_kat"]
    return is_input_key_pressed(keys, gamepad_buttons)

def is_r_kat_pressed(player_num: PlayerNum = PlayerNum.ALL) -> bool:
    """Check if the right kat button is pressed"""
    if player_num == PlayerNum.ALL:
        keys = global_data.config["keys_1p"]["right_kat"] + global_data.config["keys_2p"]["right_kat"]
    elif player_num == PlayerNum.P1:
        keys = global_data.config["keys_1p"]["right_kat"]
    elif player_num == PlayerNum.P2:
        keys = global_data.config["keys_2p"]["right_kat"]
    else:
        return False
    gamepad_buttons = global_data.config["gamepad"]["right_kat"]
    return is_input_key_pressed(keys, gamepad_buttons)

global_tex = TextureWrapper()

text_cache = set()
if not Path('cache/image').exists():
    if not Path('cache').exists():
        Path('cache').mkdir()
    Path('cache/image').mkdir()

for file in Path('cache/image').iterdir():
    text_cache.add(file.stem)

class OutlinedText:
    """Create an outlined text object."""
    def __init__(self, text: str, font_size: int, color: ray.Color, outline_thickness=5.0, vertical=False):
        """
        Create an outlined text object.

        Args:
            text (str): The text to be displayed.
            font_size (int): The size of the font.
            color (ray.Color): The color of the text.
            outline_color (ray.Color): The color of the outline.
            outline_thickness (float): The thickness of the outline.
            vertical (bool): Whether the text is vertical or not.
        """
        self.text = text
        self.hash = self._hash_text(text, font_size, color, vertical)
        self.outline_thickness = outline_thickness * global_tex.screen_scale
        self.vertical = vertical
        if self.hash in text_cache:
            self.texture = ray.load_texture(f'cache/image/{self.hash}.png')
        else:
            self.font = self._load_font_for_text(text)
            if vertical:
                self.texture = self._create_text_vertical(text, font_size, color, ray.BLANK, self.font)
            else:
                self.texture = self._create_text_horizontal(text, font_size, color, ray.BLANK, self.font)
        ray.gen_texture_mipmaps(self.texture)
        ray.set_texture_filter(self.texture, ray.TextureFilter.TEXTURE_FILTER_TRILINEAR)
        outline_size = ray.ffi.new('float*', self.outline_thickness)
        texture_size = ray.ffi.new("float[2]", [self.texture.width, self.texture.height])

        self.shader = ray.load_shader('shader/outline.vs', 'shader/outline.fs')
        self.outline_size_loc = ray.get_shader_location(self.shader, "outlineSize")
        self.outline_color_loc = ray.get_shader_location(self.shader, "outlineColor")
        self.texture_size_loc = ray.get_shader_location(self.shader, "textureSize")
        self.alpha_loc = ray.get_shader_location(self.shader, "alpha")
        ray.set_shader_value(self.shader, self.outline_size_loc, outline_size, SHADER_UNIFORM_FLOAT)
        ray.set_shader_value(self.shader, self.texture_size_loc, texture_size, SHADER_UNIFORM_VEC2)

        self.default_src = ray.Rectangle(0, 0, self.texture.width, self.texture.height)

    def _hash_text(self, text: str, font_size: int, color: ray.Color, vertical: bool):
        n = hashlib.sha256()
        n.update(text.encode('utf-8'))
        n.update(str(font_size).encode('utf-8'))
        if isinstance(color, tuple):
            n.update(str(color[0]).encode('utf-8'))
            n.update(str(color[1]).encode('utf-8'))
            n.update(str(color[2]).encode('utf-8'))
            n.update(str(color[3]).encode('utf-8'))
        else:
            n.update(str(color.r).encode('utf-8'))
            n.update(str(color.g).encode('utf-8'))
            n.update(str(color.b).encode('utf-8'))
            n.update(str(color.a).encode('utf-8'))
        n.update(str(vertical).encode('utf-8'))
        return n.hexdigest()

    def _load_font_for_text(self, text: str) -> ray.Font:
        reload_font = False
        for character in text:
            if character not in global_data.font_codepoints:
                global_data.font_codepoints.add(character)
                reload_font = True
        if reload_font:
            codepoint_count = ray.ffi.new('int *', 0)
            codepoints = ray.load_codepoints(''.join(global_data.font_codepoints), codepoint_count)
            global_data.font = ray.load_font_ex(str(Path('Graphics/Modified-DFPKanteiryu-XB.ttf')), 40, codepoints, len(global_data.font_codepoints))
            logger.info(f"Reloaded font with {len(global_data.font_codepoints)} codepoints")
        return global_data.font

    def _create_text_vertical(self, text: str, font_size: int, color: ray.Color, bg_color: ray.Color, font: Optional[ray.Font]=None, padding: int=10):
        rotate_chars = {'-', '‐', '|', '/', '\\', 'ー', '～', '~', '（', '）', '(', ')',
                        '「', '」', '[', ']', '［', '］', '【', '】', '…', '→', '→', ':', '：'}
        side_punctuation = {'.', ',', '。', '、', "'", '"', '´', '`'}
        horizontal_punct = {'?', '!', '？', '！', '†'}  # Characters that should be drawn horizontally when repeated
        lowercase_kana = {
                'ぁ', 'ア','ぃ', 'イ','ぅ', 'ウ','ぇ', 'エ','ぉ', 'オ',
                'ゃ', 'ャ','ゅ', 'ュ','ょ', 'ョ','っ', 'ッ','ゎ', 'ヮ',
                'ヶ', 'ヵ','ㇰ','ㇱ','ㇲ','ㇳ','ㇴ','ㇵ','ㇶ','ㇷ','ㇸ',
                'ㇹ','ㇺ','ㇻ','ㇼ','ㇽ','ㇾ','ㇿ'
            }

        # Group consecutive horizontal punctuation marks
        def group_horizontal_sequences(text):
            groups = []
            i = 0
            while i < len(text):
                if text[i] in horizontal_punct:
                    # Start of a horizontal sequence
                    sequence = text[i]
                    j = i + 1
                    # Continue collecting consecutive horizontal punctuation
                    while j < len(text) and text[j] in horizontal_punct:
                        sequence += text[j]
                        j += 1

                    # Only treat as horizontal if there are 2 or more characters
                    if len(sequence) >= 2:
                        groups.append(('horizontal', sequence))
                    else:
                        groups.append(('single', sequence))
                    i = j
                else:
                    groups.append(('single', text[i]))
                    i += 1
            return groups

        # Helper function to calculate adjusted character height
        def get_char_height(char):
            if char in side_punctuation:
                return font_size // 4
            elif char.islower() or char in lowercase_kana:
                return font_size * 0.88
            elif char.isspace():
                return font_size * 0.6
            else:
                return font_size

        grouped_text = group_horizontal_sequences(text)

        # Calculate dimensions with proper height adjustments
        max_char_width = 0
        total_height = padding * 2

        for group_type, content in grouped_text:
            if group_type == 'horizontal':
                # For horizontal sequences, measure the combined width
                if font:
                    seq_size = ray.measure_text_ex(font, content, font_size, 0)
                else:
                    seq_width = ray.measure_text(content, font_size)
                    seq_size = ray.Vector2(seq_width, font_size)
                max_char_width = max(max_char_width, seq_size.x)
                total_height += font_size  # Horizontal sequences use full font_size
            else:
                # Single character
                char = content
                if font:
                    char_size = ray.measure_text_ex(font, char, font_size, 0)
                else:
                    char_width = ray.measure_text(char, font_size)
                    char_size = ray.Vector2(char_width, font_size)

                if char in rotate_chars:
                    effective_width = char_size.y
                else:
                    effective_width = char_size.x
                max_char_width = max(max_char_width, effective_width)

                # Use the adjusted height instead of fixed font_size
                total_height += get_char_height(char)

        width = int(max_char_width + (padding * 2))
        height = int(total_height)  # Make sure it's an integer
        image = ray.gen_image_color(width, height, bg_color)

        curr_char_y = padding - font_size

        for group_type, content in grouped_text:
            if group_type == 'horizontal':
                # Handle horizontal punctuation sequence
                char_y = font_size
                curr_char_y += char_y

                if font:
                    seq_size = ray.measure_text_ex(font, content, font_size, 0)
                    seq_image = ray.image_text_ex(font, content, font_size, 0, color)
                else:
                    seq_width = ray.measure_text(content, font_size)
                    seq_size = ray.Vector2(seq_width, font_size)
                    seq_image = ray.image_text(content, font_size, color)

                # Center the horizontal sequence
                char_x = width // 2 - seq_size.x // 2

                ray.image_draw(image, seq_image,
                            ray.Rectangle(0, 0, seq_image.width, seq_image.height),
                            ray.Rectangle(char_x, curr_char_y, seq_image.width, seq_image.height),
                            ray.WHITE)
                ray.unload_image(seq_image)

            else:
                # Handle single character (existing logic)
                char = content
                char_y = get_char_height(char)  # Use the helper function
                curr_char_y += char_y

                if font:
                    char_size = ray.measure_text_ex(font, char, font_size, 0)
                    char_image = ray.image_text_ex(font, char, font_size, 0, color)
                else:
                    char_width = ray.measure_text(char, font_size)
                    char_size = ray.Vector2(char_width, font_size)
                    char_image = ray.image_text(char, font_size, color)

                if char in rotate_chars:
                    rotated_image = ray.gen_image_color(char_image.height, char_image.width, ray.BLANK)
                    for y in range(char_image.height):
                        for x in range(char_image.width):
                            src_color = ray.get_image_color(char_image, x, y)
                            new_x = char_image.height - 1 - y
                            new_y = x
                            ray.image_draw_pixel(rotated_image, new_x, new_y, src_color)
                    ray.unload_image(char_image)
                    char_image = rotated_image
                    effective_width = char_size.y
                else:
                    effective_width = char_size.x

                char_x = width // 2 - effective_width // 2
                if char in side_punctuation:
                    char_x += font_size//3

                ray.image_draw(image, char_image,
                            ray.Rectangle(0, 0, char_image.width, char_image.height),
                            ray.Rectangle(char_x, curr_char_y, char_image.width, char_image.height),
                            ray.WHITE)
                ray.unload_image(char_image)

        ray.export_image(image, f'cache/image/{self.hash}.png')
        texture = ray.load_texture_from_image(image)
        ray.unload_image(image)
        return texture

    def _create_text_horizontal(self, text: str, font_size: int, color: ray.Color, bg_color: ray.Color, font: Optional[ray.Font]=None, padding: int=10):
        if font:
            text_size = ray.measure_text_ex(font, text, font_size, 0)
            total_width = text_size.x + (padding * 2)
            total_height = text_size.y + (padding * 2)
        else:
            total_width = ray.measure_text(text, font_size) + (padding * 2)
            total_height = font_size + (padding * 2)
        image = ray.gen_image_color(int(total_width), int(total_height), bg_color)
        if font:
            text_image = ray.image_text_ex(font, text, font_size, 0, color)
        else:
            text_image = ray.image_text(text, font_size, color)
        text_x = padding
        text_y = padding
        ray.image_draw(image, text_image,
                    ray.Rectangle(0, 0, text_image.width, text_image.height),
                    ray.Rectangle(text_x, text_y, text_image.width, text_image.height),
                    ray.WHITE)
        ray.unload_image(text_image)

        ray.export_image(image, f'cache/image/{self.hash}.png')
        texture = ray.load_texture_from_image(image)
        ray.unload_image(image)
        return texture

    def draw(self, outline_color: ray.Color=ray.BLANK, color: ray.Color=ray.WHITE, scale: float = 1.0, center: bool = False,
            x: float = 0, y: float = 0, x2: float = 0, y2: float = 0,
            origin: ray.Vector2 = ray.Vector2(0,0), rotation: float = 0, fade: float = 1.1) -> None:
        """
        Wrapper function for raylib's draw_texture_pro().
        Parameters:
            outline_color (ray.Color): The color to outline the text.
            color (ray.Color): The color to tint the text.
            x (float): An x-value added to the top-left corner of the text.
            y (float): The y-value added to the top-left corner of the text.
            x2 (float): The x-value added to the bottom-right corner of the text.
            y2 (float): The y-value added to the bottom-right corner of the text.
            origin (ray.Vector2): The origin point of the text.
            rotation (float): The rotation angle of the text.
            fade (float): The fade factor to apply to the text.
        """
        if isinstance(outline_color, tuple):
            outline_color_alloc = ray.ffi.new("float[4]", [
                outline_color[0] / 255.0,
                outline_color[1] / 255.0,
                outline_color[2] / 255.0,
                outline_color[3] / 255.0
            ])
        else:
            outline_color_alloc = ray.ffi.new("float[4]", [
                outline_color.r / 255.0,
                outline_color.g / 255.0,
                outline_color.b / 255.0,
                outline_color.a / 255.0
            ])
        ray.set_shader_value(self.shader, self.outline_color_loc, outline_color_alloc, SHADER_UNIFORM_VEC4)
        if isinstance(color, tuple):
            alpha_value = ray.ffi.new('float*', min(fade * 255, color[3]) / 255.0)
        else:
            alpha_value = ray.ffi.new('float*', min(fade * 255, color.a) / 255.0)
        if fade != 1.1:
            final_color = ray.fade(color, fade)
        else:
            final_color = color
        ray.set_shader_value(self.shader, self.alpha_loc, alpha_value, SHADER_UNIFORM_FLOAT)
        if not self.vertical:
            offset = (10 * global_tex.screen_scale)-10
        else:
            offset = 0
        dest_rect = ray.Rectangle(x, y+offset, self.texture.width+x2, self.texture.height+y2)
        if self.outline_thickness > 0:
            ray.begin_shader_mode(self.shader)
        ray.draw_texture_pro(self.texture, self.default_src, dest_rect, origin, rotation, final_color)
        if self.outline_thickness > 0:
            ray.end_shader_mode()

    def unload(self):
        """
        Unload the outlined text object.

        Args:
            None
        """
        ray.unload_shader(self.shader)
        ray.unload_texture(self.texture)
