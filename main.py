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

    ray.set_window_max_size(screen_width, screen_height)
    ray.set_window_min_size(screen_width, screen_height)
    ray.init_window(screen_width, screen_height, "PyTaiko")

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

    start_song = False
    while not ray.window_should_close():
        ray.begin_drawing()
        ray.clear_background(ray.WHITE)

        if ray.is_key_pressed(ray.KeyboardKey.KEY_F11):
            ray.toggle_fullscreen()

        screen = screen_mapping[current_screen]
        if screen == game_screen and not start_song:
            game_screen.init_tja(sys.argv[1], sys.argv[2])
            start_song = True
        next_screen = screen.update()
        screen.draw()

        if next_screen is not None:
            current_screen = next_screen

        ray.draw_fps(20, 20)
        ray.end_drawing()
    ray.close_window()
    ray.close_audio_device()

if __name__ == "__main__":
    main()
