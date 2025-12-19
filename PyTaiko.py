import logging
import os
from pathlib import Path
import sys
import argparse

import sqlite3

import pyray as ray
from raylib.defines import (
    RL_FUNC_ADD,
    RL_ONE,
    RL_ONE_MINUS_SRC_ALPHA,
    RL_SRC_ALPHA,
)

from libs.audio import audio
from libs.global_data import PlayerNum
from libs.screen import Screen
from libs.song_hash import DB_VERSION
from libs.tja import TJAParser
from libs.utils import (
    force_dedicated_gpu,
    get_current_ms,
    global_data,
    global_tex
)
from libs.config import get_config
from scenes.devtest import DevScreen
from scenes.entry import EntryScreen
from scenes.game import GameScreen
from scenes.dan.game_dan import DanGameScreen
from scenes.practice.game import PracticeGameScreen
from scenes.practice.song_select import PracticeSongSelectScreen
from scenes.two_player.game import TwoPlayerGameScreen
from scenes.two_player.result import TwoPlayerResultScreen
from scenes.loading import LoadScreen
from scenes.result import ResultScreen
from scenes.settings import SettingsScreen
from scenes.song_select import SongSelectScreen
from scenes.title import TitleScreen
from scenes.two_player.song_select import TwoPlayerSongSelectScreen
from scenes.dan.dan_select import DanSelectScreen
from scenes.dan.dan_result import DanResultScreen

from pypresence.presence import Presence


logger = logging.getLogger(__name__)
DISCORD_APP_ID = '1451423960401973353'
try:
    RPC = Presence(DISCORD_APP_ID)
    RPC.connect()
    discord_connected = True
except Exception as e:
    discord_connected = False
    logger.warning(f"Could not connect to Discord: {e}")

class Screens:
    TITLE = "TITLE"
    ENTRY = "ENTRY"
    SONG_SELECT = "SONG_SELECT"
    GAME = "GAME"
    GAME_2P = "GAME_2P"
    RESULT = "RESULT"
    RESULT_2P = "RESULT_2P"
    SONG_SELECT_2P = "SONG_SELECT_2P"
    DAN_SELECT = "DAN_SELECT"
    GAME_DAN = "GAME_DAN"
    DAN_RESULT = "DAN_RESULT"
    PRACTICE_SELECT = "PRACTICE_SELECT"
    GAME_PRACTICE = "GAME_PRACTICE"
    SETTINGS = "SETTINGS"
    DEV_MENU = "DEV_MENU"
    LOADING = "LOADING"

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record = logging.makeLogRecord(record.__dict__)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

class DedupHandler(logging.Handler):
    def __init__(self, handler, show_count=True):
        super().__init__()
        self.handler = handler
        self.last_log = None
        self.duplicate_count = 0
        self.show_count = show_count

    def emit(self, record):
        current_log = (record.levelno, record.name, record.getMessage())

        if current_log == self.last_log:
            self.duplicate_count += 1
        else:
            if self.duplicate_count > 0 and self.show_count:
                dup_record = logging.LogRecord(
                    record.name, logging.INFO, "", 0,
                    f"(previous message repeated {self.duplicate_count} time{'s' if self.duplicate_count > 1 else ''})",
                    (), None
                )
                self.handler.emit(dup_record)

            self.handler.emit(record)
            self.last_log = current_log
            self.duplicate_count = 0

    def setFormatter(self, fmt):
        self.handler.setFormatter(fmt)

def handle_exception(exc_type, exc_value, exc_traceback):
    """Log uncaught exceptions"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def create_song_db():
    """Create the scores database if it doesn't exist"""
    with sqlite3.connect('scores.db') as con:
        cursor = con.cursor()

        cursor.execute('''
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='Scores'
        ''')
        table_exists = cursor.fetchone() is not None

        create_table_query = '''
        CREATE TABLE IF NOT EXISTS Scores (
            hash TEXT PRIMARY KEY,
            en_name TEXT NOT NULL,
            jp_name TEXT NOT NULL,
            diff INTEGER,
            score INTEGER,
            good INTEGER,
            ok INTEGER,
            bad INTEGER,
            drumroll INTEGER,
            combo INTEGER,
            clear INTEGER
        );
        '''
        cursor.execute(create_table_query)

        if not table_exists:
            cursor.execute(f'PRAGMA user_version = {DB_VERSION}')
            logger.info(f"Scores database created successfully with version {DB_VERSION}")
        else:
            logger.info("Scores database already exists")

        con.commit()

def update_camera_for_window_size(camera, virtual_width, virtual_height):
    """Update camera zoom, offset, scale, and rotation to maintain aspect ratio"""
    screen_width = ray.get_screen_width()
    screen_height = ray.get_screen_height()

    if screen_width == 0 or screen_height == 0:
        camera.zoom = 1.0
        camera.offset = ray.Vector2(0, 0)
        camera.rotation = 0.0
        return

    scale = min(screen_width / virtual_width, screen_height / virtual_height)

    base_offset_x = (screen_width - (virtual_width * scale)) * 0.5
    base_offset_y = (screen_height - (virtual_height * scale)) * 0.5

    camera.zoom = scale * global_data.camera.zoom

    zoom_offset_x = (virtual_width * scale * (global_data.camera.zoom - 1.0)) * 0.5
    zoom_offset_y = (virtual_height * scale * (global_data.camera.zoom - 1.0)) * 0.5

    h_scale = global_data.camera.h_scale
    v_scale = global_data.camera.v_scale

    h_scale_offset_x = (virtual_width * scale * (h_scale - 1.0)) * 0.5
    v_scale_offset_y = (virtual_height * scale * (v_scale - 1.0)) * 0.5

    camera.offset = ray.Vector2(
        base_offset_x - zoom_offset_x - h_scale_offset_x + (global_data.camera.offset.x * scale),
        base_offset_y - zoom_offset_y - v_scale_offset_y + (global_data.camera.offset.y * scale)
    )

    camera.rotation = global_data.camera.rotation

def main():
    force_dedicated_gpu()
    global_data.config = get_config()
    log_level = global_data.config["general"]["log_level"]
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    colored_formatter = ColoredFormatter('[%(levelname)s] %(name)s: %(message)s')
    plain_formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(colored_formatter)

    file_handler = logging.FileHandler("latest.log", encoding='utf-8')
    file_handler.setFormatter(plain_formatter)
    file_handler = DedupHandler(file_handler)
    logging.basicConfig(
        level=log_level,
        handlers=[console_handler, file_handler]
    )
    sys.excepthook = handle_exception
    logger.info("Starting PyTaiko")

    logger.debug(f"Loaded config: {global_data.config}")
    screen_width = global_tex.screen_width
    screen_height = global_tex.screen_height

    if global_data.config["video"]["vsync"]:
        ray.set_config_flags(ray.ConfigFlags.FLAG_VSYNC_HINT)
        logger.info("VSync enabled")
    if global_data.config["video"]["target_fps"] != -1:
        ray.set_target_fps(global_data.config["video"]["target_fps"])
        logger.info(f"Target FPS set to {global_data.config['video']['target_fps']}")
    ray.set_config_flags(ray.ConfigFlags.FLAG_MSAA_4X_HINT)
    ray.set_config_flags(ray.ConfigFlags.FLAG_WINDOW_RESIZABLE)
    ray.set_trace_log_level(ray.TraceLogLevel.LOG_WARNING)

    ray.init_window(screen_width, screen_height, "PyTaiko")
    logger.info(f"Window initialized: {screen_width}x{screen_height}")
    global_tex.load_screen_textures('global')
    logger.info("Global screen textures loaded")
    global_tex.load_zip('chara', 'chara_0')
    global_tex.load_zip('chara', 'chara_1')
    logger.info("Chara textures loaded")
    if global_data.config["video"]["borderless"]:
        ray.toggle_borderless_windowed()
        logger.info("Borderless window enabled")
    if global_data.config["video"]["fullscreen"]:
        ray.toggle_fullscreen()
        logger.info("Fullscreen enabled")

    current_screen = Screens.LOADING

    if len(sys.argv) == 1:
        pass
    else:
        parser = argparse.ArgumentParser(description='Launch game with specified song file')
        parser.add_argument('song_path', type=str, help='Path to the TJA song file')
        parser.add_argument('difficulty', type=int, nargs='?', default=None,
                            help='Difficulty level (optional, defaults to max difficulty)')
        parser.add_argument('--auto', action='store_true',
                            help='Enable auto mode')
        parser.add_argument('--practice', action='store_true',
                            help='Start in practice mode')
        args = parser.parse_args()
        path = Path(args.song_path)
        if not path.exists():
            parser.error(f"Song file not found: {args.song_path}")
        else:
            path = Path(os.path.abspath(path))
            tja = TJAParser(path)
            if args.difficulty is not None:
                if args.difficulty not in tja.metadata.course_data.keys():
                    parser.error(f"Invalid difficulty: {args.difficulty}. Available: {list(tja.metadata.course_data.keys())}")
                selected_difficulty = args.difficulty
            else:
                selected_difficulty = max(tja.metadata.course_data.keys())
            current_screen = Screens.GAME_PRACTICE if args.practice else Screens.GAME
            global_data.session_data[PlayerNum.P1].selected_song = path
            global_data.session_data[PlayerNum.P1].selected_difficulty = selected_difficulty
            global_data.modifiers[PlayerNum.P1].auto = args.auto

    logger.info(f"Initial screen: {current_screen}")

    audio.set_log_level((log_level-1)//10)
    old_stderr = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    audio.init_audio_device()
    os.dup2(old_stderr, 2)
    os.close(old_stderr)
    logger.info("Audio device initialized")

    create_song_db()

    title_screen = TitleScreen('title')
    entry_screen = EntryScreen('entry')
    song_select_screen = SongSelectScreen('song_select')
    song_select_screen_2p = TwoPlayerSongSelectScreen('song_select')
    load_screen = LoadScreen('loading')
    game_screen = GameScreen('game')
    game_screen_2p = TwoPlayerGameScreen('game')
    game_screen_practice = PracticeGameScreen('game')
    practice_select_screen = PracticeSongSelectScreen('song_select')
    result_screen = ResultScreen('result')
    result_screen_2p = TwoPlayerResultScreen('result')
    settings_screen = SettingsScreen('settings')
    dev_screen = DevScreen('dev')
    dan_select_screen = DanSelectScreen('dan_select')
    game_screen_dan = DanGameScreen('game_dan')
    dan_result_screen = DanResultScreen('dan_result')

    screen_mapping: dict[str, Screen] = {
        Screens.ENTRY: entry_screen,
        Screens.TITLE: title_screen,
        Screens.SONG_SELECT: song_select_screen,
        Screens.SONG_SELECT_2P: song_select_screen_2p,
        Screens.PRACTICE_SELECT: practice_select_screen,
        Screens.GAME: game_screen,
        Screens.GAME_2P: game_screen_2p,
        Screens.GAME_PRACTICE: game_screen_practice,
        Screens.RESULT: result_screen,
        Screens.RESULT_2P: result_screen_2p,
        Screens.SETTINGS: settings_screen,
        Screens.DEV_MENU: dev_screen,
        Screens.DAN_SELECT: dan_select_screen,
        Screens.GAME_DAN: game_screen_dan,
        Screens.DAN_RESULT: dan_result_screen,
        Screens.LOADING: load_screen
    }

    camera = ray.Camera2D()
    camera.target = ray.Vector2(0, 0)
    camera.rotation = 0.0
    update_camera_for_window_size(camera, screen_width, screen_height)
    logger.info("Camera2D initialized")

    ray.rl_set_blend_factors_separate(RL_SRC_ALPHA, RL_ONE_MINUS_SRC_ALPHA, RL_ONE, RL_ONE_MINUS_SRC_ALPHA, RL_FUNC_ADD, RL_FUNC_ADD)
    ray.set_exit_key(global_data.config["keys"]["exit_key"])

    ray.hide_cursor()
    logger.info("Cursor hidden")
    last_fps = 1
    last_color = ray.BLACK

    while not ray.window_should_close():
        if discord_connected:
            if global_data.session_data[global_data.player_num].selected_song != Path():
                details = f"Playing Song: {global_data.session_data[global_data.player_num].song_title}"
            else:
                details = "Idling"
            RPC.update(
                state=f"In Screen {current_screen}",
                details=details,
                large_text="PyTaiko",
                start=get_current_ms()/1000,
                buttons=[{"label": "Play Now", "url": "https://github.com/Yonokid/PyTaiko"}]
            )

        if ray.is_key_pressed(global_data.config["keys"]["fullscreen_key"]):
            ray.toggle_fullscreen()
            logger.info("Toggled fullscreen")
        elif ray.is_key_pressed(global_data.config["keys"]["borderless_key"]):
            ray.toggle_borderless_windowed()
            logger.info("Toggled borderless windowed mode")

        update_camera_for_window_size(camera, screen_width, screen_height)

        ray.begin_drawing()

        if global_data.camera.border_color != last_color:
            ray.clear_background(global_data.camera.border_color)
            last_color = global_data.camera.border_color

        ray.begin_mode_2d(camera)
        ray.begin_blend_mode(ray.BlendMode.BLEND_CUSTOM_SEPARATE)

        screen = screen_mapping[current_screen]

        next_screen = screen.update()
        if screen.screen_init:
            screen._do_draw()

        if next_screen is not None:
            logger.info(f"Screen changed from {current_screen} to {next_screen}")
            current_screen = next_screen
            global_data.input_locked = 0

        if global_data.config["general"]["fps_counter"]:
            curr_fps = ray.get_fps()
            if curr_fps != 0 and curr_fps != last_fps:
                last_fps = curr_fps
            if last_fps < 30:
                ray.draw_text(f'{last_fps} FPS', 20, 20, 20, ray.RED)
            elif last_fps < 60:
                ray.draw_text(f'{last_fps} FPS', 20, 20, 20, ray.YELLOW)
            else:
                ray.draw_text(f'{last_fps} FPS', 20, 20, 20, ray.LIME)

        ray.draw_rectangle(-screen_width, 0, screen_width, screen_height, last_color)
        ray.draw_rectangle(screen_width, 0, screen_width, screen_height, last_color)
        ray.draw_rectangle(0, -screen_height, screen_width, screen_height, last_color)
        ray.draw_rectangle(0, screen_height, screen_width, screen_height, last_color)

        ray.end_blend_mode()
        ray.end_mode_2d()
        ray.end_drawing()

    ray.close_window()
    audio.close_audio_device()
    if discord_connected:
        RPC.close()
    logger.info("Window closed and audio device shut down")

if __name__ == "__main__":
    main()
