import copy
import json
import os
import logging
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

import raylib as ray
from pyray import Vector2, Rectangle, Color

from libs.animation import BaseAnimation, parse_animations

from libs.config import get_config

logger = logging.getLogger(__name__)

class SkinInfo:
    def __init__(self, x: float, y: float, font_size: int, width: float, height: float):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.font_size = font_size

class Texture:
    """Texture class for managing textures and animations."""
    def __init__(self, name: str, texture: Any, init_vals: dict[str, int]):
        self.name = name
        self.texture = texture
        self.init_vals = init_vals
        if isinstance(self.texture, list):
            self.width = self.texture[0].width
            self.height = self.texture[0].height
        else:
            self.width = self.texture.width
            self.height = self.texture.height
        self.is_frames = isinstance(self.texture, list)
        if isinstance(self.texture, list):
            pass
            for texture_data in self.texture:
                ray.GenTextureMipmaps(ray.ffi.addressof(texture_data))
                ray.SetTextureFilter(texture_data, ray.TEXTURE_FILTER_TRILINEAR)
                ray.SetTextureWrap(texture_data, ray.TEXTURE_WRAP_CLAMP)
        else:
            ray.GenTextureMipmaps(ray.ffi.addressof(self.texture))
            ray.SetTextureFilter(self.texture, ray.TEXTURE_FILTER_TRILINEAR)
            ray.SetTextureWrap(self.texture, ray.TEXTURE_WRAP_CLAMP)

        self.x: list[int] = [0]
        self.y: list[int] = [0]
        self.x2: list[int] = [self.width]
        self.y2: list[int] = [self.height]
        self.controllable: list[bool] = [False]

class TextureWrapper:
    """Texture wrapper class for managing textures and animations."""
    def __init__(self):
        self.textures: dict[str, dict[str, Texture]] = dict()
        self.animations: dict[int, BaseAnimation] = dict()
        self.skin_config: dict[str, SkinInfo] = dict()
        self.graphics_path = Path(get_config()['paths']['graphics_path'])
        self.parent_graphics_path = Path(get_config()['paths']['graphics_path'])
        if not (self.graphics_path / "skin_config.json").exists():
            raise Exception("skin is missing a skin_config.json")

        data = json.loads((self.graphics_path / "skin_config.json").read_text())
        self.skin_config: dict[str, SkinInfo] = {
            k: SkinInfo(v.get('x', 0), v.get('y', 0), v.get('font_size', 0), v.get('width', 0), v.get('height', 0)) for k, v in data.items()
        }
        self.screen_width = int(self.skin_config["screen"].width)
        self.screen_height = int(self.skin_config["screen"].height)
        self.screen_scale = self.screen_width / 1280
        if "parent" in data["screen"]:
            parent = data["screen"]["parent"]
            self.parent_graphics_path = Path("Graphics") / parent
            parent_data = json.loads((self.parent_graphics_path / "skin_config.json").read_text())
            for k, v in parent_data.items():
                self.skin_config[k] = SkinInfo(v.get('x', 0) * self.screen_scale, v.get('y', 0) * self.screen_scale, v.get('font_size', 0) * self.screen_scale, v.get('width', 0) * self.screen_scale, v.get('height', 0) * self.screen_scale)

    def unload_textures(self):
        """Unload all textures and animations."""
        ids = {}  # Map ID to texture name
        for zip in self.textures:
            for file in self.textures[zip]:
                tex_object = self.textures[zip][file]
                if isinstance(tex_object.texture, list):
                    for i, texture in enumerate(tex_object.texture):
                        if texture.id in ids:
                            logger.warning(f"Duplicate texture ID {texture.id}: {ids[texture.id]} and {zip}/{file}[{i}]")
                        else:
                            ids[texture.id] = f"{zip}/{file}[{i}]"
                            ray.UnloadTexture(texture)
                else:
                    if tex_object.texture.id in ids:
                        logger.warning(f"Duplicate texture ID {tex_object.texture.id}: {ids[tex_object.texture.id]} and {zip}/{file}")
                    else:
                        ids[tex_object.texture.id] = f"{zip}/{file}"
                        ray.UnloadTexture(tex_object.texture)

        self.textures.clear()
        self.animations.clear()

        logger.info("All textures unloaded")

    def get_animation(self, index: int, is_copy: bool = False):
        """Get an animation by ID and returns a reference.
        Returns a copy of the animation if is_copy is True."""
        if index not in self.animations:
            raise Exception(f"Unable to find id {index} in loaded animations")
        if is_copy:
            new_anim = copy.deepcopy(self.animations[index])
            if self.animations[index].loop:
                new_anim.start()
            return new_anim
        if self.animations[index].loop:
            self.animations[index].start()
        return self.animations[index]

    def _read_tex_obj_data(self, tex_mapping: dict | list, tex_object: Texture):
        if isinstance(tex_mapping, list):
            for i in range(len(tex_mapping)):
                if i == 0:
                    tex_object.x[i] = tex_mapping[i].get("x", 0)
                    tex_object.y[i] = tex_mapping[i].get("y", 0)
                    tex_object.x2[i] = tex_mapping[i].get("x2", tex_object.width)
                    tex_object.y2[i] = tex_mapping[i].get("y2", tex_object.height)
                    tex_object.controllable[i] = tex_mapping[i].get("controllable", False)
                else:
                    tex_object.x.append(tex_mapping[i].get("x", 0))
                    tex_object.y.append(tex_mapping[i].get("y", 0))
                    tex_object.x2.append(tex_mapping[i].get("x2", tex_object.width))
                    tex_object.y2.append(tex_mapping[i].get("y2", tex_object.height))
                    tex_object.controllable.append(tex_mapping[i].get("controllable", False))
        else:
            tex_object.x = [tex_mapping.get("x", 0)]
            tex_object.y = [tex_mapping.get("y", 0)]
            tex_object.x2 = [tex_mapping.get("x2", tex_object.width)]
            tex_object.y2 = [tex_mapping.get("y2", tex_object.height)]
            tex_object.controllable = [tex_mapping.get("controllable", False)]

    def load_animations(self, screen_name: str):
        """Load animations for a screen, falling back to parent if not found."""
        screen_path = self.graphics_path / screen_name
        parent_screen_path = self.parent_graphics_path / screen_name

        if (screen_path / 'animation.json').exists():
            with open(screen_path / 'animation.json') as json_file:
                self.animations = parse_animations(json.loads(json_file.read()))
            logger.info(f"Animations loaded for screen: {screen_name}")
        elif self.parent_graphics_path != self.graphics_path and (parent_screen_path / 'animation.json').exists():
            with open(parent_screen_path / 'animation.json') as json_file:
                anim_json = json.loads(json_file.read())
                for anim in anim_json:
                    if "total_distance" in anim and not isinstance(anim["total_distance"], dict):
                        anim["total_distance"] = anim["total_distance"] * self.screen_scale
                self.animations = parse_animations(anim_json)
            logger.info(f"Animations loaded for screen: {screen_name} (from parent)")

    def load_zip(self, screen_name: str, subset: str):
        """Load textures from child zip, using parent texture.json if child doesn't have one."""
        zip_path = (self.graphics_path / screen_name / subset).with_suffix('.zip')
        parent_zip_path = (self.parent_graphics_path / screen_name / subset).with_suffix('.zip')

        if screen_name in self.textures and subset in self.textures[screen_name]:
            return

        # Child zip must exist
        if not zip_path.exists():
            logger.warning(f"Zip file not found: {subset} for screen {screen_name}")
            return

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Try to get texture.json from child first, then parent
                tex_mapping_data = None
                texture_json_source = "child"

                if 'texture.json' in zip_ref.namelist():
                    with zip_ref.open('texture.json') as json_file:
                        tex_mapping_data = json.loads(json_file.read().decode('utf-8'))
                elif self.parent_graphics_path != self.graphics_path and parent_zip_path.exists():
                    # Fall back to parent's texture.json
                    with zipfile.ZipFile(parent_zip_path, 'r') as parent_zip_ref:
                        if 'texture.json' in parent_zip_ref.namelist():
                            with parent_zip_ref.open('texture.json') as json_file:
                                tex_mapping_data = json.loads(json_file.read().decode('utf-8'))
                                for tex_map in tex_mapping_data:
                                    for key in tex_mapping_data[tex_map]:
                                        if key in ["x", "y", "x2", "y2"]:
                                            tex_mapping_data[tex_map][key] = tex_mapping_data[tex_map][key] * self.screen_scale
                            texture_json_source = "parent"
                        else:
                            raise Exception(f"texture.json file missing from both {zip_path} and {parent_zip_path}")
                else:
                    raise Exception(f"texture.json file missing from {zip_path}")

                self.textures[zip_path.stem] = dict()

                encoding = sys.getfilesystemencoding()
                for tex_name in tex_mapping_data:
                    if f"{tex_name}/" in zip_ref.namelist():
                        tex_mapping = tex_mapping_data[tex_name]

                        with tempfile.TemporaryDirectory() as temp_dir:
                            zip_ref.extractall(temp_dir, members=[name for name in zip_ref.namelist()
                                                                if name.startswith(tex_name)])

                            extracted_path = Path(temp_dir) / tex_name
                            if extracted_path.is_dir():
                                frames = [ray.LoadTexture(str(frame).encode(encoding)) for frame in sorted(extracted_path.iterdir(),
                                            key=lambda x: int(x.stem)) if frame.is_file()]
                            else:
                                frames = [ray.LoadTexture(str(extracted_path).encode(encoding))]
                        self.textures[zip_path.stem][tex_name] = Texture(tex_name, frames, tex_mapping)
                        self._read_tex_obj_data(tex_mapping, self.textures[zip_path.stem][tex_name])
                    elif f"{tex_name}.png" in zip_ref.namelist():
                        tex_mapping = tex_mapping_data[tex_name]

                        png_filename = f"{tex_name}.png"
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                            temp_file.write(zip_ref.read(png_filename))
                            temp_path = temp_file.name

                        try:
                            tex = ray.LoadTexture(temp_path.encode(encoding))
                            self.textures[zip_path.stem][tex_name] = Texture(tex_name, tex, tex_mapping)
                            self._read_tex_obj_data(tex_mapping, self.textures[zip_path.stem][tex_name])
                        finally:
                            os.unlink(temp_path)
                    else:
                        logger.error(f"Texture {tex_name} was not found in {zip_path}")

            json_note = f" (texture.json from {texture_json_source})" if texture_json_source == "parent" else ""
            logger.info(f"Textures loaded from zip: {zip_path}{json_note}")
        except Exception as e:
            logger.error(f"Failed to load textures from zip {zip_path}: {e}")

    def load_screen_textures(self, screen_name: str) -> None:
        """Load textures for a screen."""
        screen_path = self.graphics_path / screen_name

        if not screen_path.exists():
            logger.warning(f"Textures for Screen {screen_name} do not exist")
            return

        # Load animations
        self.load_animations(screen_name)

        # Load zip files from child screen path only
        for zip_file in screen_path.iterdir():
            if zip_file.is_file() and zip_file.suffix == ".zip":
                self.load_zip(screen_name, zip_file.stem)

        logger.info(f"Screen textures loaded for: {screen_name}")

    def control(self, tex_object: Texture, index: int = 0):
        '''debug function'''
        distance = 1
        if ray.IsKeyDown(ray.KEY_LEFT_SHIFT):
            distance = 10
        if ray.IsKeyPressed(ray.KEY_LEFT):
            tex_object.x[index] -= distance
            logger.info(f"{tex_object.name}: {tex_object.x[index]}, {tex_object.y[index]}")
        if ray.IsKeyPressed(ray.KEY_RIGHT):
            tex_object.x[index] += distance
            logger.info(f"{tex_object.name}: {tex_object.x[index]}, {tex_object.y[index]}")
        if ray.IsKeyPressed(ray.KEY_UP):
            tex_object.y[index] -= distance
            logger.info(f"{tex_object.name}: {tex_object.x[index]}, {tex_object.y[index]}")
        if ray.IsKeyPressed(ray.KEY_DOWN):
            tex_object.y[index] += distance
            logger.info(f"{tex_object.name}: {tex_object.x[index]}, {tex_object.y[index]}")

    def clear_screen(self, color: Color):
        if isinstance(color, tuple):
            clear_color = [color[0], color[1], color[2], color[3]]
        else:
            clear_color = [color.r, color.g, color.b, color.a]
        ray.ClearBackground(clear_color)

    def _draw_texture_untyped(self, subset: str, texture: str, color: tuple[int, int, int, int], frame: int, scale: float, center: bool,
                            mirror: str, x: float, y: float, x2: float, y2: float,
                            origin: tuple[float, float], rotation: float, fade: float,
                            index: int, src: Optional[tuple[float, float, float, float]], controllable: bool) -> None:
        if subset not in self.textures:
            return
        if texture not in self.textures[subset]:
            return
        mirror_x = -1 if mirror == 'horizontal' else 1
        mirror_y = -1 if mirror == 'vertical' else 1
        if fade != 1.1:
            final_color = ray.Fade(color, fade)
        else:
            final_color = color
        tex_object = self.textures[subset][texture]
        if src is not None:
            source_rect = src
        else:
            source_rect = (0, 0, tex_object.width * mirror_x, tex_object.height * mirror_y)
        if center:
            dest_rect = (tex_object.x[index] + (tex_object.width//2) - ((tex_object.width * scale)//2) + x, tex_object.y[index] + (tex_object.height//2) - ((tex_object.height * scale)//2) + y, tex_object.x2[index]*scale + x2, tex_object.y2[index]*scale + y2)
        else:
            dest_rect = (tex_object.x[index] + x, tex_object.y[index] + y, tex_object.x2[index]*scale + x2, tex_object.y2[index]*scale + y2)

        if tex_object.is_frames:
            if not isinstance(tex_object.texture, list):
                raise Exception("Texture was marked as multiframe but is only 1 texture")
            if frame >= len(tex_object.texture):
                raise Exception(f"Frame {frame} not available in iterable texture {tex_object.name}")
            ray.DrawTexturePro(tex_object.texture[frame], source_rect, dest_rect, origin, rotation, final_color)
        else:
            if isinstance(tex_object.texture, list):
                raise Exception("Texture is multiframe but was called as 1 texture")
            ray.DrawTexturePro(tex_object.texture, source_rect, dest_rect, origin, rotation, final_color)
        if tex_object.controllable[index] or controllable:
            self.control(tex_object)

    def draw_texture(self, subset: str, texture: str, color: Color = Color(255, 255, 255, 255), frame: int = 0, scale: float = 1.0, center: bool = False,
                            mirror: str = '', x: float = 0, y: float = 0, x2: float = 0, y2: float = 0,
                            origin: Vector2 = Vector2(0,0), rotation: float = 0, fade: float = 1.1,
                            index: int = 0, src: Optional[Rectangle] = None, controllable: bool = False) -> None:
        """
        Wrapper function for raylib's draw_texture_pro().
        Parameters:
            subset (str): The subset of textures to use.
            texture (str): The name of the texture to draw.
            color (ray.Color): The color to tint the texture.
            frame (int): The frame of the texture to draw. Only used if the texture is animated.
            scale (float): The scale factor to apply to the texture.
            center (bool): Whether to center the texture.
            mirror (str): The direction to mirror the texture, either 'horizontal' or 'vertical'.
            x (float): An x-value added to the top-left corner of the texture.
            y (float): The y-value added to the top-left corner of the texture.
            x2 (float): The x-value added to the bottom-right corner of the texture.
            y2 (float): The y-value added to the bottom-right corner of the texture.
            origin (ray.Vector2): The origin point of the texture.
            rotation (float): The rotation angle of the texture.
            fade (float): The fade factor to apply to the texture.
            index (int): The index of the position data for the texture. Only used if the texture has multiple positions.
            src (Optional[ray.Rectangle]): The source rectangle of the texture.
            controllable (bool): Whether the texture is controllable.
        """
        if src is not None:
            src_data = (src.x, src.y, src.width, src.height)
        else:
            src_data = None
        if isinstance(color, tuple):
            color_data = (color[0], color[1], color[2], color[3])
        else:
            color_data = (color.r, color.g, color.b, color.a)
        self._draw_texture_untyped(subset, texture, color_data, frame, scale, center, mirror, x, y, x2, y2, (origin.x, origin.y), rotation, fade, index, src_data, controllable)

tex = TextureWrapper()
