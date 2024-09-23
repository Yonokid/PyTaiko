import pyray as ray
from global_funcs import load_texture_from_zip

class EntryScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height

        self.texture_footer = load_texture_from_zip('Graphics\\lumendata\\entry.zip', 'entry_img00375.png')

    def update(self):
        if ray.is_key_pressed(ray.KeyboardKey.KEY_ENTER):
            return "GAME"
        return None

    def draw(self):
        ray.draw_texture(self.texture_footer, 0, self.height - 151, ray.WHITE)
