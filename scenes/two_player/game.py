import logging
import copy
from pathlib import Path
from libs.global_data import PlayerNum
from libs.tja import TJAParser
from libs.utils import get_current_ms
from libs.audio import audio
from libs.utils import global_data
from libs.video import VideoPlayer
import pyray as ray
from scenes.game import ClearAnimation, FCAnimation, FailAnimation, GameScreen, Player, Background, ResultTransition

logger = logging.getLogger(__name__)

class TwoPlayerGameScreen(GameScreen):
    def on_screen_start(self):
        super().on_screen_start()
        scene_preset = self.tja.metadata.scene_preset
        if self.background is not None:
            self.background.unload()
        self.background = Background(PlayerNum.TWO_PLAYER, self.bpm, scene_preset=scene_preset)
        self.result_transition = ResultTransition(PlayerNum.TWO_PLAYER)

    def load_hitsounds(self):
        """Load the hit sounds"""
        sounds_dir = Path("Sounds")

        # Load hitsounds for 1P
        if global_data.hit_sound[PlayerNum.P1] == -1:
            audio.load_sound(Path('none.wav'), 'hitsound_don_1p')
            audio.load_sound(Path('none.wav'), 'hitsound_kat_1p')
            logger.info("Loaded default (none) hit sounds for 1P")
        elif global_data.hit_sound[PlayerNum.P1] == 0:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "don.wav", 'hitsound_don_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "ka.wav", 'hitsound_kat_1p')
            logger.info("Loaded wav hit sounds for 1P")
        else:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "don.ogg", 'hitsound_don_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "ka.ogg", 'hitsound_kat_1p')
            logger.info("Loaded ogg hit sounds for 1P")
        audio.set_sound_pan('hitsound_don_1p', 0.0)
        audio.set_sound_pan('hitsound_kat_1p', 0.0)

        # Load hitsounds for 2P
        if global_data.hit_sound[PlayerNum.P2] == -1:
            audio.load_sound(Path('none.wav'), 'hitsound_don_2p')
            audio.load_sound(Path('none.wav'), 'hitsound_kat_2p')
            logger.info("Loaded default (none) hit sounds for 2P")
        elif global_data.hit_sound[PlayerNum.P2] == 0:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "don_2p.wav", 'hitsound_don_2p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "ka_2p.wav", 'hitsound_kat_2p')
            logger.info("Loaded wav hit sounds for 2P")
        else:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "don.ogg", 'hitsound_don_2p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "ka.ogg", 'hitsound_kat_2p')
            logger.info("Loaded ogg hit sounds for 2P")
        audio.set_sound_pan('hitsound_don_2p', 1.0)
        audio.set_sound_pan('hitsound_kat_2p', 1.0)

    def global_keys(self):
        if ray.is_key_pressed(ray.KeyboardKey.KEY_F1):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            self.init_tja(global_data.session_data[global_data.player_num].selected_song)
            audio.play_sound('restart', 'sound')
            self.song_started = False
            logger.info("F1 pressed: song restarted")

        if ray.is_key_pressed(ray.KeyboardKey.KEY_ESCAPE):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            logger.info("Escape pressed: returning to SONG_SELECT_2P")
            return self.on_screen_end('SONG_SELECT_2P')

    def init_tja(self, song: Path):
        """Initialize the TJA file"""
        self.tja = TJAParser(song, start_delay=self.start_delay)
        if self.tja.metadata.bgmovie != Path() and self.tja.metadata.bgmovie.exists():
            self.movie = VideoPlayer(self.tja.metadata.bgmovie)
            self.movie.set_volume(0.0)
        else:
            self.movie = None
        global_data.session_data[PlayerNum.P1].song_title = self.tja.metadata.title.get(global_data.config['general']['language'].lower(), self.tja.metadata.title['en'])
        if self.tja.metadata.wave.exists() and self.tja.metadata.wave.is_file() and self.song_music is None:
            self.song_music = audio.load_music_stream(self.tja.metadata.wave, 'song')

        tja_copy = copy.deepcopy(self.tja)
        self.player_1 = Player(self.tja, PlayerNum.P1, global_data.session_data[PlayerNum.P1].selected_difficulty, False, global_data.modifiers[PlayerNum.P1])
        self.player_2 = Player(tja_copy, PlayerNum.P2, global_data.session_data[PlayerNum.P2].selected_difficulty, True, global_data.modifiers[PlayerNum.P2])
        self.start_ms = (get_current_ms() - self.tja.metadata.offset*1000)
        logger.info(f"TJA initialized for two-player song: {song}")

    def spawn_ending_anims(self):
        if global_data.session_data[PlayerNum.P1].result_data.bad == 0:
            self.player_1.ending_anim = FCAnimation(self.player_1.is_2p)
        elif self.player_1.gauge.is_clear:
            self.player_1.ending_anim = ClearAnimation(self.player_1.is_2p)
        elif not self.player_1.gauge.is_clear:
            self.player_1.ending_anim = FailAnimation(self.player_1.is_2p)

        if global_data.session_data[PlayerNum.P2].result_data.bad == 0:
            self.player_2.ending_anim = FCAnimation(self.player_2.is_2p)
        elif self.player_2.gauge.is_clear:
            self.player_2.ending_anim = ClearAnimation(self.player_2.is_2p)
        elif not self.player_2.gauge.is_clear:
            self.player_2.ending_anim = FailAnimation(self.player_2.is_2p)

    def update(self):
        super(GameScreen, self).update()
        current_time = get_current_ms()
        self.transition.update(current_time)
        self.current_ms = current_time - self.start_ms
        if self.transition.is_finished:
            self.start_song(self.current_ms)
        else:
            self.start_ms = current_time - self.tja.metadata.offset*1000
        self.update_background(current_time)

        if self.song_music is not None:
            audio.update_music_stream(self.song_music)

        self.player_1.update(self.current_ms, current_time, self.background)
        self.player_2.update(self.current_ms, current_time, self.background)
        self.song_info.update(current_time)
        self.result_transition.update(current_time)
        if self.result_transition.is_finished and not audio.is_sound_playing('result_transition'):
            return self.on_screen_end('RESULT_2P')
        elif self.current_ms >= self.player_1.end_time:
            session_data = global_data.session_data[PlayerNum.P1]
            session_data.result_data.score, session_data.result_data.good, session_data.result_data.ok, session_data.result_data.bad, session_data.result_data.max_combo, session_data.result_data.total_drumroll = self.player_1.get_result_score()
            session_data.result_data.gauge_length = int(self.player_1.gauge.gauge_length)
            session_data = global_data.session_data[PlayerNum.P2]
            session_data.result_data.score, session_data.result_data.good, session_data.result_data.ok, session_data.result_data.bad, session_data.result_data.max_combo, session_data.result_data.total_drumroll = self.player_2.get_result_score()
            session_data.result_data.gauge_length = int(self.player_2.gauge.gauge_length)
            if self.end_ms != 0:
                if current_time >= self.end_ms + 1000:
                    if self.player_1.ending_anim is None:
                        self.write_score()
                        self.spawn_ending_anims()
                if current_time >= self.end_ms + 8533.34:
                    if not self.result_transition.is_started:
                        self.result_transition.start()
                        audio.play_sound('result_transition', 'voice')
            else:
                self.end_ms = current_time

        return self.global_keys()

    def update_background(self, current_time):
        if self.movie is not None:
            self.movie.update()
        else:
            if len(self.player_1.current_bars) > 0:
                self.bpm = self.player_1.bpm
            if self.background is not None:
                self.background.update(current_time, self.bpm, self.player_1.gauge, self.player_2.gauge)

    def draw(self):
        if self.movie is not None:
            self.movie.draw()
        elif self.background is not None:
            self.background.draw()
        self.player_1.draw(self.current_ms, self.start_ms, self.mask_shader)
        self.player_2.draw(self.current_ms, self.start_ms, self.mask_shader)
        self.draw_overlay()
