import pyray as ray
import sys

from entry import *
from game import *
from title import *

class Screens:
    TITLE = "TITLE"
    ENTRY = "ENTRY"
    SONG_SELECT = "SONG_SELECT"
    GAME = "GAME"
    RESULT = "RESULT"

def main():
    screen_width = 1280
    screen_height = 720

    ray.set_config_flags(ray.ConfigFlags.FLAG_VSYNC_HINT)
    ray.set_config_flags(ray.ConfigFlags.FLAG_MSAA_4X_HINT)

    ray.set_window_max_size(screen_width, screen_height)
    ray.set_window_min_size(screen_width, screen_height)
    ray.init_window(screen_width, screen_height, "PyTaiko")
    #ray.toggle_borderless_windowed()
    ray.clear_window_state(ray.ConfigFlags.FLAG_WINDOW_TOPMOST)
    #ray.maximize_window()

    current_screen = Screens.TITLE
    frames_counter = 0

    ray.init_audio_device()

    title_screen = TitleScreen(screen_width, screen_height)
    entry_screen = EntryScreen(screen_width, screen_height)
    game_screen = GameScreen(screen_width, screen_height)

    screen_mapping = {
        Screens.ENTRY: entry_screen,
        Screens.TITLE: title_screen,
        #Screens.SONG_SELECT: song_select_screen,
        Screens.GAME: game_screen,
        #Screens.RESULT: result_screen
    }
    target = ray.load_render_texture(screen_width, screen_height)
    ray.set_texture_filter(target.texture, ray.TextureFilter.TEXTURE_FILTER_TRILINEAR)
    #lmaooooooooooooo
    ray.rl_set_blend_factors_separate(0x302, 0x303, 1, 0x303, 0x8006, 0x8006)
    start_song = False
    ray.set_exit_key(ray.KeyboardKey.KEY_A)
    while not ray.window_should_close():

        ray.begin_texture_mode(target)
        ray.begin_blend_mode(ray.BlendMode.BLEND_CUSTOM_SEPARATE)
        screen = screen_mapping[current_screen]

        if ray.is_key_pressed(ray.KeyboardKey.KEY_F11):
            ray.toggle_fullscreen()
            ray.is_window_fullscreen()
        elif ray.is_key_pressed(ray.KeyboardKey.KEY_F12):
            ray.toggle_borderless_windowed()

        if screen == game_screen and not start_song:
            game_screen.init_tja(sys.argv[1], sys.argv[2])
            start_song = True
        next_screen = screen.update()
        screen.draw()
        if screen == title_screen:
            ray.clear_background(ray.BLACK)
        else:
            ray.clear_background(ray.WHITE)

        if next_screen is not None:
            current_screen = next_screen

        ray.draw_fps(20, 20)
        ray.end_blend_mode()
        ray.end_texture_mode()
        ray.begin_drawing()
        ray.clear_background(ray.WHITE)
        ray.draw_texture_pro(target.texture, ray.Rectangle(0, 0, target.texture.width, -target.texture.height), ray.Rectangle(0, 0, ray.get_render_width(), ray.get_render_height()), ray.Vector2(0,0), 0, ray.WHITE)
        ray.end_drawing()
    ray.close_window()
    ray.close_audio_device()

if __name__ == "__main__":
    main()
