import logging
import platform
import pyray as ray
from pathlib import Path

import cffi

from libs.config import VolumeConfig, get_config

ffi = cffi.FFI()

ffi.cdef("""
    typedef int PaHostApiIndex;
    // Forward declarations
    struct audio_buffer;

    // Type definitions
    typedef struct wave {
        unsigned int frameCount;
        unsigned int sampleRate;
        unsigned int sampleSize;
        unsigned int channels;
        void *data;
    } wave;

    typedef struct audio_stream {
        struct audio_buffer *buffer;
        unsigned int sampleRate;
        unsigned int sampleSize;
        unsigned int channels;
    } audio_stream;

    typedef struct sound {
        audio_stream stream;
        unsigned int frameCount;
    } sound;

    typedef struct music {
        audio_stream stream;
        unsigned int frameCount;
        void *ctxData;
    } music;

    void set_log_level(int level);

    // Device management
    void list_host_apis(void);
    const char* get_host_api_name(PaHostApiIndex hostApi);
    void init_audio_device(PaHostApiIndex host_api, double sample_rate, unsigned long buffer_size);
    void close_audio_device(void);
    bool is_audio_device_ready(void);
    void set_master_volume(float volume);
    float get_master_volume(void);

    // Wave management
    wave load_wave(const char* filename);
    bool is_wave_valid(wave wave);
    void unload_wave(wave wave);

    // Sound management
    sound load_sound_from_wave(wave wave);
    sound load_sound(const char* filename);
    bool is_sound_valid(sound sound);
    void unload_sound(sound sound);
    void play_sound(sound sound);
    void pause_sound(sound sound);
    void resume_sound(sound sound);
    void stop_sound(sound sound);
    bool is_sound_playing(sound sound);
    void set_sound_volume(sound sound, float volume);
    void set_sound_pitch(sound sound, float pitch);
    void set_sound_pan(sound sound, float pan);

    // Audio stream management
    audio_stream load_audio_stream(unsigned int sample_rate, unsigned int sample_size, unsigned int channels);
    void unload_audio_stream(audio_stream stream);
    void play_audio_stream(audio_stream stream);
    void pause_audio_stream(audio_stream stream);
    void resume_audio_stream(audio_stream stream);
    bool is_audio_stream_playing(audio_stream stream);
    void stop_audio_stream(audio_stream stream);
    void set_audio_stream_volume(audio_stream stream, float volume);
    void set_audio_stream_pitch(audio_stream stream, float pitch);
    void set_audio_stream_pan(audio_stream stream, float pan);
    void update_audio_stream(audio_stream stream, const void *data, int frame_count);

    // Music management
    music load_music_stream(const char* filename);
    bool is_music_valid(music music);
    void unload_music_stream(music music);
    void play_music_stream(music music);
    void pause_music_stream(music music);
    void resume_music_stream(music music);
    void stop_music_stream(music music);
    void seek_music_stream(music music, float position);
    bool music_stream_needs_update(music music);
    void update_music_stream(music music);
    bool is_music_stream_playing(music music);
    void set_music_volume(music music, float volume);
    void set_music_pitch(music music, float pitch);
    void set_music_pan(music music, float pan);
    float get_music_time_length(music music);
    float get_music_time_played(music music);

    // Memory management
    void free(void *ptr);
""")

logger = logging.getLogger(__name__)

try:
    if platform.system() == "Windows":
        lib = ffi.dlopen("libaudio.dll")
    elif platform.system() == "Darwin":
        lib = ffi.dlopen("./libaudio.dylib")
    else:  # Assume Linux/Unix
        lib = ffi.dlopen("./libaudio.so")
except OSError as e:
    logger.error(f"Failed to load shared library: {e}")
    raise

class AudioEngine:
    """Initialize an audio engine for playing sounds and music."""
    def __init__(self, device_type: int, sample_rate: float, buffer_size: int,
                 volume_presets: VolumeConfig, sounds_path: Path | None = None):
        self.device_type = max(device_type, 0)
        if sample_rate < 0:
            self.target_sample_rate = 44100
        else:
            self.target_sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.sounds = {}
        self.music_streams = {}
        self.audio_device_ready = False
        self.volume_presets = volume_presets
        self.lib = lib

        if sounds_path is None:
            self.sounds_path = Path(f"Skins/{get_config()['paths']['skin']}/Sounds")
        else:
            self.sounds_path = sounds_path

    def set_log_level(self, level: int):
        self.lib.set_log_level(level) # type: ignore

    def list_host_apis(self):
        """Prints a list of available host APIs to the console"""
        self.lib.list_host_apis() # type: ignore

    def get_host_api_name(self, api_id: int) -> str:
        """Returns the name of the host API with the given ID"""
        result = self.lib.get_host_api_name(api_id) # type: ignore
        if result == ffi.NULL:
            return ""
        result = ffi.string(result)
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        return result

    def init_audio_device(self) -> bool:
        """Initialize the audio device"""
        try:
            self.lib.init_audio_device(self.device_type, self.target_sample_rate, self.buffer_size) # type: ignore
            self.audio_device_ready = self.lib.is_audio_device_ready() # type: ignore
            file_path_str = str(self.sounds_path / 'don.wav').encode('utf-8')
            self.don = self.lib.load_sound(file_path_str) # type: ignore
            file_path_str = str(self.sounds_path / 'ka.wav').encode('utf-8')
            self.kat = self.lib.load_sound(file_path_str) # type: ignore
            if self.audio_device_ready:
                logger.info("Audio device initialized successfully")
            return self.audio_device_ready
        except Exception as e:
            logger.error(f"Failed to initialize audio device: {e}")
            return False

    def close_audio_device(self) -> None:
        """Close the audio device"""
        try:
            # Clean up all sounds and music
            for sound_id in list(self.sounds.keys()):
                self.unload_sound(sound_id)
            for music_id in list(self.music_streams.keys()):
                self.unload_music_stream(music_id)

            self.lib.unload_sound(self.don) # type: ignore
            self.lib.unload_sound(self.kat) # type: ignore
            self.lib.close_audio_device() # type: ignore
            self.audio_device_ready = False
            logger.info("Audio device closed")
        except Exception as e:
            logger.error(f"Error closing audio device: {e}")

    def is_audio_device_ready(self) -> bool:
        """Check if audio device is ready"""
        return self.lib.is_audio_device_ready() # type: ignore

    def set_master_volume(self, volume: float) -> None:
        """Set master volume (0.0 to 1.0)"""
        self.lib.set_master_volume(max(0.0, min(1.0, volume))) # type: ignore

    def get_master_volume(self) -> float:
        """Get master volume"""
        return self.lib.get_master_volume() # type: ignore

    # Sound management
    def load_sound(self, file_path: Path, name: str) -> str:
        """Load a sound file and return sound ID"""
        try:
            if platform.system() == 'Windows':
                # Use Windows ANSI codepage (cp932 for Japanese)
                file_path_str = str(file_path).encode('cp932', errors='replace')
            else:
                file_path_str = str(file_path).encode('utf-8')
            sound = self.lib.load_sound(file_path_str) # type: ignore

            if not self.lib.is_sound_valid(sound): # type: ignore
                file_path_str = str(file_path).encode('utf-8')
                sound = self.lib.load_sound(file_path_str) # type: ignore

            if self.lib.is_sound_valid(sound): # type: ignore
                self.sounds[name] = sound
                return name
            else:
                logger.error(f"Failed to load sound: {file_path}")
                return ""
        except Exception as e:
            logger.error(f"Error loading sound {file_path}: {e}")
            return ""

    def unload_sound(self, name: str) -> None:
        """Unload a sound by name"""
        if name in self.sounds:
            self.lib.unload_sound(self.sounds[name]) # type: ignore
            del self.sounds[name]
        else:
            logger.warning(f"Sound {name} not found")

    def load_screen_sounds(self, screen_name: str) -> None:
        """Load sounds for a given screen"""
        path = self.sounds_path / screen_name
        if not path.exists():
            logger.warning(f"Sounds for screen {screen_name} not found")
            return
        for sound in path.iterdir():
            if sound.is_dir():
                for file in sound.iterdir():
                    self.load_sound(file, sound.stem + '_' + file.stem)
            if sound.is_file():
                self.load_sound(sound, sound.stem)

        path = self.sounds_path / 'global'
        for sound in path.iterdir():
            if sound.is_dir():
                for file in sound.iterdir():
                    self.load_sound(file, sound.stem + '_' + file.stem)
            if sound.is_file():
                self.load_sound(sound, sound.stem)

    def unload_all_sounds(self):
        """Unload all sounds"""
        for name in list(self.sounds.keys()):
            self.unload_sound(name)

    def play_sound(self, name: str, volume_preset: str) -> None:
        """Play a sound"""
        if name == 'don':
            if volume_preset:
                self.lib.set_sound_volume(self.don, self.volume_presets[volume_preset]) # type: ignore
            self.lib.play_sound(self.don) # type: ignore
        elif name == 'kat':
            if volume_preset:
                self.lib.set_sound_volume(self.kat, self.volume_presets[volume_preset]) # type: ignore
            self.lib.play_sound(self.kat) # type: ignore
        elif name in self.sounds:
            sound = self.sounds[name]
            if volume_preset:
                self.lib.set_sound_volume(sound, self.volume_presets[volume_preset]) # type: ignore
            self.lib.play_sound(sound) # type: ignore
        else:
            logger.warning(f"Sound {name} not found")

    def stop_sound(self, name: str) -> None:
        """Stop a sound"""
        if name == 'don':
            self.lib.stop_sound(self.don) # type: ignore
        elif name == 'kat':
            self.lib.stop_sound(self.kat) # type: ignore
        if name in self.sounds:
            sound = self.sounds[name]
            self.lib.stop_sound(sound) # type: ignore
        else:
            logger.warning(f"Sound {name} not found")

    def is_sound_playing(self, name: str) -> bool:
        """Check if a sound is playing"""
        if name == 'don':
            return self.lib.is_sound_playing(self.don) # type: ignore
        elif name == 'kat':
            return self.lib.is_sound_playing(self.kat) # type: ignore
        if name in self.sounds:
            sound = self.sounds[name]
            return self.lib.is_sound_playing(sound) # type: ignore
        else:
            logger.warning(f"Sound {name} not found")
            return False

    def set_sound_volume(self, name: str, volume: float) -> None:
        """Set the volume of a specific sound"""
        if name == 'don':
            self.lib.set_sound_volume(self.don, volume) # type: ignore
        elif name == 'kat':
            self.lib.set_sound_volume(self.kat, volume) # type: ignore
        elif name in self.sounds:
            sound = self.sounds[name]
            self.lib.set_sound_volume(sound, volume) # type: ignore
        else:
            logger.warning(f"Sound {name} not found")

    def set_sound_pan(self, name: str, pan: float) -> None:
        """Set the pan of a specific sound"""
        if name == 'don':
            self.lib.set_sound_pan(self.don, pan) # type: ignore
        elif name == 'kat':
            self.lib.set_sound_pan(self.kat, pan) # type: ignore
        elif name in self.sounds:
            sound = self.sounds[name]
            self.lib.set_sound_pan(sound, pan) # type: ignore
        else:
            logger.warning(f"Sound {name} not found")

    # Music management
    def load_music_stream(self, file_path: Path, name: str) -> str:
        """Load a music stream and return music ID"""
        if platform.system() == 'Windows':
            # Use Windows ANSI codepage (cp932 for Japanese)
            file_path_str = str(file_path).encode('cp932', errors='replace')
        else:
            file_path_str = str(file_path).encode('utf-8')

        music = self.lib.load_music_stream(file_path_str) # type: ignore

        if not self.lib.is_music_valid(music): # type: ignore
            file_path_str = str(file_path).encode('utf-8')
            music = self.lib.load_music_stream(file_path_str) # type: ignore

        if self.lib.is_music_valid(music): # type: ignore
            self.music_streams[name] = music
            logger.info(f"Loaded music stream from {file_path} as {name}")
            return name
        else:
            logger.error(f"Failed to load music: {file_path}")
            return ""

    def play_music_stream(self, name: str, volume_preset: str) -> None:
        """Play a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.seek_music_stream(music, 0) # type: ignore
            if volume_preset:
                self.lib.set_music_volume(music, self.volume_presets[volume_preset]) # type: ignore
            self.lib.play_music_stream(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")

    def music_stream_needs_update(self, name: str) -> bool:
        """Check if a music stream needs updating (buffers need refilling)"""
        if name in self.music_streams:
            music = self.music_streams[name]
            return self.lib.music_stream_needs_update(music) # type: ignore
        return False

    def update_music_stream(self, name: str) -> None:
        """Update a music stream (only if buffers need refilling)"""
        if name in self.music_streams:
            music = self.music_streams[name]
            if self.lib.music_stream_needs_update(music): # type: ignore
                self.lib.update_music_stream(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")

    def get_music_time_length(self, name: str) -> float:
        """Get the time length of a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            return self.lib.get_music_time_length(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")
            return 0.0

    def get_music_time_played(self, name: str) -> float:
        """Get the time played of a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            return self.lib.get_music_time_played(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")
            return 0.0

    def set_music_volume(self, name: str, volume: float) -> None:
        """Set the volume of a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.set_music_volume(music, volume) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")

    def is_music_stream_playing(self, name: str) -> bool:
        """Check if a music stream is playing"""
        if name in self.music_streams:
            music = self.music_streams[name]
            return self.lib.is_music_stream_playing(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")
            return False

    def stop_music_stream(self, name: str) -> None:
        """Stop a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.stop_music_stream(music) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")

    def unload_music_stream(self, name: str) -> None:
        """Unload a music stream"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.unload_music_stream(music) # type: ignore
            del self.music_streams[name]
        else:
            logger.warning(f"Music stream {name} not found")

    def unload_all_music(self) -> None:
        """Unload all music streams"""
        for music_id in list(self.music_streams.keys()):
            self.unload_music_stream(music_id)

    def seek_music_stream(self, name: str, position: float) -> None:
        """Seek a music stream to a specific position"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.seek_music_stream(music, position) # type: ignore
        else:
            logger.warning(f"Music stream {name} not found")

class AudioEngineLegacy(AudioEngine):
    def __init__(self, device_type: int, sample_rate: float, buffer_size: int,
                 volume_presets: VolumeConfig, sounds_path: Path | None = None):
        super().__init__(device_type, sample_rate, buffer_size, volume_presets, sounds_path)
        self.lib = ray

    def set_log_level(self, level: int):
        pass

    def list_host_apis(self):
        """Prints a list of available host APIs to the console"""
        pass

    def get_host_api_name(self, api_id: int) -> str:
        """Returns the name of the host API with the given ID"""
        return ''

    def init_audio_device(self) -> bool:
        """Initialize the audio device"""
        try:
            self.lib.init_audio_device()
            self.audio_device_ready = self.lib.is_audio_device_ready()
            file_path_str = str(self.sounds_path / 'don.wav')
            self.don = self.lib.load_sound(file_path_str)
            file_path_str = str(self.sounds_path / 'ka.wav')
            self.kat = self.lib.load_sound(file_path_str)
            if self.audio_device_ready:
                logger.info("Audio device initialized successfully")
            return self.audio_device_ready
        except Exception as e:
            logger.error(f"Failed to initialize audio device: {e}")
            return False

    def load_sound(self, file_path: Path, name: str) -> str:
        """Load a sound file and return sound ID"""
        try:
            sound = self.lib.load_sound(str(file_path))
            if self.lib.is_sound_valid(sound):
                self.sounds[name] = sound
                return name
            else:
                logger.error(f"Failed to load sound: {file_path}")
                return ""
        except Exception as e:
            logger.error(f"Error loading sound {file_path}: {e}")
            return ""

    def load_music_stream(self, file_path: Path, name: str) -> str:
        """Load a music stream and return music ID"""
        music = self.lib.load_music_stream(str(file_path))
        if self.lib.is_music_valid(music):
            self.music_streams[name] = music
            logger.info(f"Loaded music stream from {file_path} as {name}")
            return name
        else:
            logger.error(f"Failed to load music: {file_path}")
            return ""

    def update_music_stream(self, name: str) -> None:
        """Update a music stream (only if buffers need refilling)"""
        if name in self.music_streams:
            music = self.music_streams[name]
            self.lib.update_music_stream(music)
        else:
            logger.warning(f"Music stream {name} not found")

# Create the global audio instance
audio = AudioEngineLegacy(get_config()["audio"]["device_type"], get_config()["audio"]["sample_rate"], get_config()["audio"]["buffer_size"], get_config()["volume"])
audio.set_master_volume(0.75)
