from pathlib import Path
import tomlkit
import json
from typing import TypedDict

import pyray as ray

class GeneralConfig(TypedDict):
    fps_counter: bool
    audio_offset: int
    visual_offset: int
    language: str
    hard_judge: int
    touch_enabled: bool
    timer_frozen: bool
    judge_counter: bool
    nijiiro_notes: bool
    log_level: int
    fake_online: bool
    practice_mode_bar_delay: int
    score_method: str

class NameplateConfig(TypedDict):
    name: str
    title: str
    title_bg: int
    dan: int
    gold: bool
    rainbow: bool

class PathsConfig(TypedDict):
    tja_path: list[Path]
    video_path: list[Path]
    graphics_path: Path

class KeysConfig(TypedDict):
    exit_key: int
    fullscreen_key: int
    borderless_key: int
    pause_key: int
    back_key: int
    restart_key: int

class Keys1PConfig(TypedDict):
    left_kat: list[int]
    left_don: list[int]
    right_don: list[int]
    right_kat: list[int]

class Keys2PConfig(TypedDict):
    left_kat: list[int]
    left_don: list[int]
    right_don: list[int]
    right_kat: list[int]

class GamepadConfig(TypedDict):
    left_kat: list[int]
    left_don: list[int]
    right_don: list[int]
    right_kat: list[int]

class AudioConfig(TypedDict):
    device_type: int
    sample_rate: int
    buffer_size: int

class VolumeConfig(TypedDict):
    sound: float
    music: float
    voice: float
    hitsound: float
    attract_mode: float

class VideoConfig(TypedDict):
    fullscreen: bool
    borderless: bool
    target_fps: int
    vsync: bool

class Config(TypedDict):
    general: GeneralConfig
    nameplate_1p: NameplateConfig
    nameplate_2p: NameplateConfig
    paths: PathsConfig
    keys: KeysConfig
    keys_1p: Keys1PConfig
    keys_2p: Keys2PConfig
    gamepad: GamepadConfig
    audio: AudioConfig
    volume: VolumeConfig
    video: VideoConfig

def get_key_string(key_code: int) -> str:
    """Convert a key code back to its string representation"""
    if 65 <= key_code <= 90:
        return chr(key_code)
    if 48 <= key_code <= 57:
        return chr(key_code)

    for attr_name in dir(ray):
        if attr_name.startswith('KEY_'):
            if getattr(ray, attr_name) == key_code:
                return attr_name[4:].lower()

    raise ValueError(f"Unknown key code: {key_code}")

def get_key_code(key: str) -> int:
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    else:
        key_code = getattr(ray, f"KEY_{key.upper()}", None)
        if key_code is None:
            raise ValueError(f"Invalid key: {key}")
        return key_code

def get_config() -> Config:
    """Get the configuration from the TOML file"""
    config_path = Path('dev-config.toml') if Path('dev-config.toml').exists() else Path('config.toml')

    with open(config_path, "r", encoding="utf-8") as f:
        config_file = tomlkit.load(f)

    config: Config = json.loads(json.dumps(config_file))
    for key in config['keys']:
        config['keys'][key] = get_key_code(config['keys'][key])
    for key in config['keys_1p']:
        bindings = config['keys_1p'][key]
        for i, bind in enumerate(bindings):
            config['keys_1p'][key][i] = get_key_code(bind)
    for key in config['keys_2p']:
        bindings = config['keys_2p'][key]
        for i, bind in enumerate(bindings):
            config['keys_2p'][key][i] = get_key_code(bind)
    return config

def save_config(config: Config) -> None:
    """Save the configuration to the TOML file"""
    config_to_save = json.loads(json.dumps(config))

    for key in config_to_save['keys']:
        config_to_save['keys'][key] = get_key_string(config_to_save['keys'][key])
    for key in config_to_save['keys_1p']:
        bindings = config_to_save['keys_1p'][key]
        for i, bind in enumerate(bindings):
            config_to_save['keys_1p'][key][i] = get_key_string(bind)
    for key in config_to_save['keys_2p']:
        bindings = config_to_save['keys_2p'][key]
        for i, bind in enumerate(bindings):
            config_to_save['keys_2p'][key][i] = get_key_string(bind)

    config_path = Path('dev-config.toml') if Path('dev-config.toml').exists() else Path('config.toml')
    with open(config_path, "w", encoding="utf-8") as f:
        tomlkit.dump(config_to_save, f)
