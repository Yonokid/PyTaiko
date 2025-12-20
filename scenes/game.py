import bisect
from enum import IntEnum
import math
import logging
import sqlite3
from collections import deque
from pathlib import Path
from typing import Optional
from itertools import chain

import pyray as ray

from libs.animation import Animation
from libs.audio import audio
from libs.background import Background
from libs.chara_2d import Chara2D
from libs.global_data import Crown, Difficulty, Modifiers, PlayerNum, ScoreMethod
from libs.global_objects import AllNetIcon, Nameplate
from libs.screen import Screen
from libs.texture import tex
from libs.tja import (
    Balloon,
    Drumroll,
    Note,
    NoteList,
    NoteType,
    TJAParser,
    TimelineObject,
    apply_modifiers,
    calculate_base_score,
)
from libs.transition import Transition
from libs.utils import (
    OutlinedText,
    get_current_ms,
    global_data,
    global_tex,
    is_l_don_pressed,
    is_l_kat_pressed,
    is_r_don_pressed,
    is_r_kat_pressed,
    rounded,
)
from libs.video import VideoPlayer

logger = logging.getLogger(__name__)

class DrumType(IntEnum):
    DON = 1
    KAT = 2

class Side(IntEnum):
    LEFT = 1
    RIGHT = 2

class Judgments(IntEnum):
    GOOD = 0
    OK = 1
    BAD = 2

class GameScreen(Screen):
    JUDGE_X = 414 * tex.screen_scale
    JUDGE_Y = 256 * tex.screen_scale
    def on_screen_start(self):
        super().on_screen_start()
        self.mask_shader = ray.load_shader("shader/outline.vs", "shader/mask.fs")
        self.current_ms = 0
        self.end_ms = 0
        self.start_delay = 1000
        self.song_started = False
        self.paused = False
        self.pause_time = 0
        self.audio_time = 0
        self.movie = None
        self.song_music = None
        if global_data.config["general"]["nijiiro_notes"]:
            # drop original
            if "notes" in tex.textures:
                del tex.textures["notes"]
            # load nijiiro, rename "notes"
            # to leave hardcoded 'notes' in calls below
            tex.load_zip("game", "notes_nijiiro")
            tex.textures["notes"] = tex.textures.pop("notes_nijiiro")
            logger.info("Loaded nijiiro notes textures")
        ray.set_shader_value_texture(self.mask_shader, ray.get_shader_location(self.mask_shader, "texture0"), tex.textures['balloon']['rainbow_mask'].texture)
        ray.set_shader_value_texture(self.mask_shader, ray.get_shader_location(self.mask_shader, "texture1"), tex.textures['balloon']['rainbow'].texture)
        session_data = global_data.session_data[global_data.player_num]
        self.init_tja(session_data.selected_song)
        logger.info(f"TJA initialized for song: {session_data.selected_song}")
        self.load_hitsounds()
        self.song_info = SongInfo(session_data.song_title, session_data.genre_index)
        self.result_transition = ResultTransition(global_data.player_num)
        subtitle = self.tja.metadata.subtitle.get(global_data.config['general']['language'].lower(), '')
        self.bpm = self.tja.metadata.bpm
        scene_preset = self.tja.metadata.scene_preset
        if self.movie is None:
            self.background = Background(global_data.player_num, self.bpm, scene_preset=scene_preset)
            logger.info("Background initialized")
        else:
            self.background = None
            logger.info("Movie initialized")
        self.transition = Transition(session_data.song_title, subtitle, is_second=True)
        self.allnet_indicator = AllNetIcon()
        self.transition.start()

    def on_screen_end(self, next_screen):
        self.song_started = False
        self.end_ms = 0
        if self.movie is not None:
            self.movie.stop()
            logger.info("Movie stopped")
        if self.background is not None:
            self.background.unload()
            logger.info("Background unloaded")
        return super().on_screen_end(next_screen)

    def load_hitsounds(self):
        """Load the hit sounds"""
        sounds_dir = Path("Sounds")
        if global_data.hit_sound == -1:
            audio.load_sound(Path('none.wav'), 'hitsound_don_1p')
            audio.load_sound(Path('none.wav'), 'hitsound_kat_1p')
            logger.info("Loaded default (none) hit sounds for 1P")
        if global_data.hit_sound == 0:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "don.wav", 'hitsound_don_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "ka.wav", 'hitsound_kat_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "don.wav", 'hitsound_don_2p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "ka.wav", 'hitsound_kat_2p')
            logger.info("Loaded wav hit sounds for 1P and 2P")
        else:
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "don.ogg", 'hitsound_don_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P1]) / "ka.ogg", 'hitsound_kat_1p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "don.ogg", 'hitsound_don_2p')
            audio.load_sound(sounds_dir / "hit_sounds" / str(global_data.hit_sound[PlayerNum.P2]) / "ka.ogg", 'hitsound_kat_2p')
            logger.info("Loaded ogg hit sounds for 1P and 2P")

    def init_tja(self, song: Path):
        """Initialize the TJA file"""
        self.tja = TJAParser(song, start_delay=self.start_delay)
        if self.tja.metadata.bgmovie != Path() and self.tja.metadata.bgmovie.exists():
            self.movie = VideoPlayer(self.tja.metadata.bgmovie)
        else:
            self.movie = None
        global_data.session_data[global_data.player_num].song_title = self.tja.metadata.title.get(global_data.config['general']['language'].lower(), self.tja.metadata.title['en'])
        if self.tja.metadata.wave.exists() and self.tja.metadata.wave.is_file() and self.song_music is None:
            self.song_music = audio.load_music_stream(self.tja.metadata.wave, 'song')

        self.player_1 = Player(self.tja, global_data.player_num, global_data.session_data[global_data.player_num].selected_difficulty, False, global_data.modifiers[global_data.player_num])
        self.start_ms = get_current_ms() - self.tja.metadata.offset*1000

    def write_score(self):
        """Write the score to the database"""
        if global_data.modifiers[global_data.player_num].auto:
            return
        with sqlite3.connect(global_data.score_db) as con:
            session_data = global_data.session_data[global_data.player_num]
            cursor = con.cursor()
            hash = session_data.song_hash
            check_query = "SELECT score, clear FROM Scores WHERE hash = ? LIMIT 1"
            cursor.execute(check_query, (hash,))
            result = cursor.fetchone()
            existing_score = result[0] if result is not None else None
            existing_crown = result[1] if result is not None and len(result) > 1 and result[1] is not None else 0
            crown = Crown.NONE
            if session_data.result_data.bad and session_data.result_data.ok == 0:
                crown = Crown.DFC
            elif session_data.result_data.bad == 0:
                crown = Crown.FC
            elif self.player_1.gauge.is_clear:
                crown = Crown.CLEAR
            logger.info(f"Existing score: {existing_score}, Existing crown: {existing_crown}, New score: {session_data.result_data.score}, New crown: {crown}")
            if result is None or (existing_score is not None and session_data.result_data.score > existing_score):
                insert_query = '''
                INSERT OR REPLACE INTO Scores (hash, en_name, jp_name, diff, score, good, ok, bad, drumroll, combo, clear)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                '''
                data = (hash, self.tja.metadata.title['en'],
                        self.tja.metadata.title.get('ja', ''), self.player_1.difficulty,
                        session_data.result_data.score, session_data.result_data.good,
                        session_data.result_data.ok, session_data.result_data.bad,
                        session_data.result_data.total_drumroll, session_data.result_data.max_combo, crown)
                cursor.execute(insert_query, data)
                session_data.result_data.prev_score = existing_score if existing_score is not None else 0
                logger.info(f"Wrote score {session_data.result_data.score} for {self.tja.metadata.title['en']}")
                con.commit()
            if result is None or (existing_crown is not None and crown > existing_crown):
                cursor.execute("UPDATE Scores SET clear = ? WHERE hash = ?", (crown, hash))
                con.commit()

    def start_song(self, ms_from_start):
        if (ms_from_start >= self.tja.metadata.offset*1000 + self.start_delay - global_data.config["general"]["audio_offset"]) and not self.song_started:
            if self.song_music is not None:
                audio.play_music_stream(self.song_music, 'music')
                logger.info(f"Song started at {ms_from_start}")
            if self.movie is not None:
                self.movie.start(get_current_ms())
                self.movie.set_volume(0.0)
            self.song_started = True

    def pause_song(self):
        self.paused = not self.paused
        if self.paused:
            if self.song_music is not None:
                self.audio_time = audio.get_music_time_played(self.song_music)
                audio.stop_music_stream(self.song_music)
            self.pause_time = get_current_ms() - self.start_ms
        else:
            if self.song_music is not None:
                audio.play_music_stream(self.song_music, 'music')
                audio.seek_music_stream(self.song_music, self.audio_time)
            self.start_ms = get_current_ms() - self.pause_time

    def global_keys(self):
        if ray.is_key_pressed(global_data.config["keys"]["restart_key"]):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            self.init_tja(global_data.session_data[global_data.player_num].selected_song)
            audio.play_sound('restart', 'sound')
            self.song_started = False

        if ray.is_key_pressed(global_data.config["keys"]["back_key"]):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            return self.on_screen_end('SONG_SELECT')

        if ray.is_key_pressed(global_data.config["keys"]["pause_key"]):
            self.pause_song()

    def spawn_ending_anims(self):
        if global_data.session_data[global_data.player_num].result_data.bad == 0:
            self.player_1.ending_anim = FCAnimation(self.player_1.is_2p)
        elif self.player_1.gauge.is_clear:
            self.player_1.ending_anim = ClearAnimation(self.player_1.is_2p)
        elif not self.player_1.gauge.is_clear:
            self.player_1.ending_anim = FailAnimation(self.player_1.is_2p)

    def update_background(self, current_time):
        if self.movie is not None:
            self.movie.update()
        else:
            if len(self.player_1.current_bars) > 0:
                self.bpm = self.player_1.bpm
            if self.background is not None:
                self.background.update(current_time, self.bpm, self.player_1.gauge, None)

    def update(self):
        super().update()
        current_time = get_current_ms()
        self.transition.update(current_time)
        if not self.paused:
            self.current_ms = current_time - self.start_ms
        if self.transition.is_finished:
            self.start_song(self.current_ms)
        else:
            self.start_ms = current_time - self.tja.metadata.offset*1000
        self.update_background(current_time)

        if self.song_music is not None:
            audio.update_music_stream(self.song_music)

        self.player_1.update(self.current_ms, current_time, self.background)
        self.song_info.update(current_time)
        self.result_transition.update(current_time)
        if self.result_transition.is_finished and not audio.is_sound_playing('result_transition'):
            logger.info("Result transition finished, moving to RESULT screen")
            return self.on_screen_end('RESULT')
        elif self.current_ms >= self.player_1.end_time:
            session_data = global_data.session_data[global_data.player_num]
            session_data.result_data.score, session_data.result_data.good, session_data.result_data.ok, session_data.result_data.bad, session_data.result_data.max_combo, session_data.result_data.total_drumroll = self.player_1.get_result_score()
            if self.player_1.gauge is not None:
                session_data.result_data.gauge_length = self.player_1.gauge.gauge_length
            if self.end_ms != 0:
                if current_time >= self.end_ms + 1000:
                    if self.player_1.ending_anim is None:
                        self.write_score()
                        logger.info("Score written and ending animations spawned")
                        self.spawn_ending_anims()
                if current_time >= self.end_ms + 8533.34:
                    if not self.result_transition.is_started:
                        self.result_transition.start()
                        audio.play_sound('result_transition', 'voice')
                        logger.info("Result transition started and voice played")
            else:
                self.end_ms = current_time

        return self.global_keys()

    def draw_overlay(self):
        self.song_info.draw()
        self.transition.draw()
        self.result_transition.draw()
        self.allnet_indicator.draw()

    def draw(self):
        if self.movie is not None:
            self.movie.draw()
        elif self.background is not None:
            self.background.draw()
        self.player_1.draw(self.current_ms, self.start_ms, self.mask_shader)
        self.draw_overlay()

class Player:
    TIMING_GOOD = 25.0250015258789
    TIMING_OK = 75.0750045776367
    TIMING_BAD = 108.441665649414

    TIMING_GOOD_EASY = 41.7083358764648
    TIMING_OK_EASY = 108.441665649414
    TIMING_BAD_EASY = 125.125

    def __init__(self, tja: TJAParser, player_num: PlayerNum, difficulty: int, is_2p: bool, modifiers: Modifiers):
        self.is_2p = is_2p
        self.is_dan = False
        self.player_num = player_num
        self.difficulty = difficulty
        self.visual_offset = global_data.config["general"]["visual_offset"]
        self.score_method = global_data.config["general"]["score_method"]
        self.modifiers = modifiers
        self.tja = tja

        self.reset_chart()

        #Score management
        self.good_count = 0
        self.ok_count = 0
        self.bad_count = 0
        self.combo = 0
        self.score = 0
        self.max_combo = 0
        self.total_drumroll = 0

        self.arc_points = 25
        self.judge_x = 0
        self.judge_y = 0

        self.draw_judge_list: list[Judgment] = []
        self.lane_hit_effect: Optional[LaneHitEffect] = None
        self.draw_arc_list: list[NoteArc] = []
        self.draw_drum_hit_list: list[DrumHitEffect] = []
        self.drumroll_counter: Optional[DrumrollCounter] = None
        self.balloon_anim: Optional[BalloonAnimation] = None
        self.kusudama_anim: Optional[KusudamaAnimation] = None
        self.base_score_list: list[ScoreCounterAnimation] = []
        self.combo_display = Combo(self.combo, 0, self.is_2p)
        self.score_counter = ScoreCounter(self.score, self.is_2p)
        self.gogo_time: Optional[GogoTime] = None
        self.delay_start: Optional[float] = None
        self.delay_end: Optional[float] = None
        self.combo_announce = ComboAnnounce(self.combo, 0, player_num, self.is_2p)
        self.branch_indicator = BranchIndicator(self.is_2p) if tja and tja.metadata.course_data[self.difficulty].is_branching else None
        self.ending_anim: Optional[FailAnimation | ClearAnimation | FCAnimation] = None
        self.is_gogo_time = False
        plate_info = global_data.config[f'nameplate_{self.is_2p+1}p']
        self.nameplate = Nameplate(plate_info['name'], plate_info['title'], global_data.player_num, plate_info['dan'], plate_info['gold'], plate_info['rainbow'], plate_info['title_bg'])
        self.chara = Chara2D(player_num - 1, self.bpm)
        if global_data.config['general']['judge_counter']:
            self.judge_counter = JudgeCounter()
        else:
            self.judge_counter = None

        self.input_log: dict[float, str] = dict()
        stars = tja.metadata.course_data[self.difficulty].level
        self.gauge = Gauge(self.player_num, self.difficulty, stars, self.total_notes, self.is_2p)
        self.gauge_hit_effect: list[GaugeHitEffect] = []

        self.autoplay_hit_side = Side.LEFT
        self.last_subdivision = -1

    def get_load_time(self, note):
        note_half_w = tex.textures["notes"]["1"].width // 2
        travel_distance = tex.screen_width - GameScreen.JUDGE_X

        base_pixels_per_ms = (note.bpm / 240000 * abs(note.scroll_x) * travel_distance)

        if base_pixels_per_ms == 0:
            base_pixels_per_ms = (note.bpm / 240000 * abs(note.scroll_y) * travel_distance)

        normal_travel_ms = (travel_distance + note_half_w) / base_pixels_per_ms

        if not hasattr(note, "sudden_appear_ms") or not hasattr(note, "sudden_moving_ms") or note.sudden_appear_ms == float("inf"):
            note.load_ms   = note.hit_ms - normal_travel_ms
            note.unload_ms = note.hit_ms + normal_travel_ms
            return

        note.load_ms = note.hit_ms - note.sudden_appear_ms
        movement_duration = note.sudden_moving_ms

        if movement_duration <= 0:
            movement_duration = normal_travel_ms

        sudden_pixels_per_ms = travel_distance / movement_duration
        unload_offset = travel_distance / sudden_pixels_per_ms
        note.unload_ms = note.hit_ms + unload_offset


    def reset_chart(self):
        notes, self.branch_m, self.branch_e, self.branch_n = self.tja.notes_to_position(self.difficulty)
        self.play_notes, self.draw_note_list, self.draw_bar_list = apply_modifiers(notes, self.modifiers)

        self.don_notes = deque([note for note in self.play_notes if note.type in {NoteType.DON, NoteType.DON_L}])
        self.kat_notes = deque([note for note in self.play_notes if note.type in {NoteType.KAT, NoteType.KAT_L}])
        self.other_notes = deque([note for note in self.play_notes if note.type not in {NoteType.DON, NoteType.DON_L, NoteType.KAT, NoteType.KAT_L}])
        self.total_notes = len([note for note in self.play_notes if 0 < note.type < 5])
        total_notes = notes
        if self.branch_m:
            for section in self.branch_m:
                self.total_notes += len([note for note in section.play_notes if 0 < note.type < 5])
                total_notes += section
        self.base_score = 0
        self.score_init = 0
        self.score_diff = 0
        if self.score_method == ScoreMethod.SHINUCHI:
            self.base_score = calculate_base_score(total_notes)
        elif self.score_method == ScoreMethod.GEN3:
            self.score_diff = self.tja.metadata.course_data[self.difficulty].scorediff
            if self.score_diff <= 0:
                logger.warning("Error: No scorediff specified or scorediff less than 0 | Using shinuchi scoring method instead")
                self.score_diff = 0

            score_init_list = self.tja.metadata.course_data[self.difficulty].scoreinit
            if len(score_init_list) <= 0:
                logger.warning("Error: No scoreinit specified or scoreinit less than 0 | Using shinuchi scoring method instead")
                self.score_init = calculate_base_score(total_notes)
                self.score_diff = 0 # in case there is a diff but not an init.
            else:
                self.score_init = score_init_list[0]
            logger.debug(f"debug | score init: {self.score_init} | score diff: {self.score_diff}")

        #Note management
        self.timeline = notes.timeline
        self.timeline_index = 0 # Range: [0, len(timeline)]
        self.current_bars: list[Note] = []
        self.current_notes_draw: list[Note | Drumroll | Balloon] = []
        self.is_drumroll = False
        self.curr_drumroll_count = 0
        self.is_balloon = False
        self.curr_balloon_count = 0
        self.is_branch = False
        self.curr_branch_reqs = []
        self.branch_condition_count = 0
        self.branch_condition = ''
        self.balloon_index = 0
        self.bpm = 120
        if self.timeline and hasattr(self.timeline[self.timeline_index], 'bpm'):
            self.bpm = self.timeline[self.timeline_index].bpm
        for note in chain(self.draw_note_list, self.draw_bar_list):
            self.get_load_time(note)

        self.draw_note_list = deque(sorted(self.draw_note_list, key=lambda n: n.load_ms))

        # Handle HBSCROLL, BMSCROLL (pre-modify hit_ms, so that notes can't be literally hit, but are still visually different) - basically it applies the transformations of #BPMCHANGE and #DELAY to hit_ms, so that notes can't be hit even if its visaulyl
        for i, o in enumerate(self.timeline):
            if hasattr(o, 'bpmchange'):
                hit_ms = o.hit_ms
                bpmchange = o.bpmchange
                for note in chain(self.draw_note_list, self.draw_bar_list):
                    if note.hit_ms > hit_ms:
                        note.hit_ms = (note.hit_ms - hit_ms) / bpmchange + hit_ms
                for i2 in range(i + 1, len(self.timeline)):
                    o2 = self.timeline[i2]
                    if not hasattr(o2, 'bpmchange'):
                        continue
                    o2.hit_ms = (o2.hit_ms - hit_ms) / bpmchange + hit_ms
            elif hasattr(o, 'delay'):
                hit_ms = o.hit_ms
                delay = o.delay
                for note in chain(self.draw_note_list, self.draw_bar_list):
                    if note.hit_ms > hit_ms:
                        note.hit_ms += delay
                for i2 in range(i + 1, len(self.timeline)):
                    o2 = self.timeline[i2]
                    if not hasattr(o2, 'delay'):
                        continue
                    o2.hit_ms += delay

        # Decide end_time after all transforms have been applied
        self.end_time = self.play_notes[-1].hit_ms if self.play_notes else 0

        for branch in (self.branch_m, self.branch_e, self.branch_n):
            if branch:
                for section in branch:
                    if section.draw_notes:
                        for note in section.draw_notes:
                            self.get_load_time(note)
                        section.draw_notes = sorted(section.draw_notes, key=lambda n: n.load_ms)
                    if section.bars:
                        for note in section.bars:
                            self.get_load_time(note)
                        section.bars = sorted(section.bars, key=lambda n: n.load_ms)
                    if section.play_notes:
                        self.end_time = max(self.end_time, section.play_notes[-1].hit_ms)

    def merge_branch_section(self, branch_section: NoteList, current_ms: float):
        """Merges the branch notes into the current notes"""
        self.play_notes.extend(branch_section.play_notes)
        self.draw_note_list.extend(branch_section.draw_notes)
        self.draw_bar_list.extend(branch_section.bars)
        self.play_notes = deque(sorted(self.play_notes))
        self.draw_note_list = deque(sorted(self.draw_note_list, key=lambda x: x.hit_ms))
        self.draw_bar_list = deque(sorted(self.draw_bar_list, key=lambda x: x.hit_ms))
        total_don = [note for note in self.play_notes if note.type in {NoteType.DON, NoteType.DON_L}]
        total_kat = [note for note in self.play_notes if note.type in {NoteType.KAT, NoteType.KAT_L}]
        total_other = [note for note in self.play_notes if note.type not in {NoteType.DON, NoteType.DON_L, NoteType.KAT, NoteType.KAT_L}]

        self.don_notes = deque([note for note in total_don if note.hit_ms > current_ms])
        self.kat_notes = deque([note for note in total_kat if note.hit_ms > current_ms])
        self.other_notes = deque([note for note in total_other if note.hit_ms > current_ms])

    def get_result_score(self):
        """Returns the score, good count, ok count, bad count, max combo, and total drumroll"""
        return self.score, self.good_count, self.ok_count, self.bad_count, self.max_combo, self.total_drumroll

    def get_position_x(self, note, current_ms):
        if self.delay_start:
            current_ms = self.delay_start
        speedx = note.bpm / 240000 * note.scroll_x * (tex.screen_width - GameScreen.JUDGE_X)
        return GameScreen.JUDGE_X + (note.hit_ms - current_ms) * speedx


    def get_position_y(self, note, current_ms):
        if self.delay_start:
            current_ms = self.delay_start
        speedy = note.bpm / 240000 * note.scroll_y * ((tex.screen_width - GameScreen.JUDGE_X)/tex.screen_width) * tex.screen_width
        return (note.hit_ms - current_ms) * speedy

    '''
    def handle_tjap3_extended_commands(self, current_ms: float):
        if not self.timeline or self.timeline_index >= len(self.timeline):
            return

        timeline_object = self.timeline[self.timeline_index]
        should_advance = False

        if hasattr(timeline_object, 'border_color') and timeline_object.hit_ms <= current_ms:
            global_data.camera.border_color = timeline_object.border_color
            should_advance = True

        if hasattr(timeline_object, 'cam_h_offset') and timeline_object.hit_ms <= current_ms:
            orig_offset = global_data.camera.offset
            global_data.camera.offset = ray.Vector2(timeline_object.cam_h_offset, orig_offset.y)
            should_advance = True

        if hasattr(timeline_object, 'cam_v_offset') and timeline_object.hit_ms <= current_ms:
            orig_offset = global_data.camera.offset
            global_data.camera.offset = ray.Vector2(orig_offset.x, timeline_object.cam_v_offset)
            should_advance = True

        if hasattr(timeline_object, 'cam_zoom') and timeline_object.hit_ms <= current_ms:
            global_data.camera.zoom = timeline_object.cam_zoom
            should_advance = True

        if hasattr(timeline_object, 'cam_h_scale') and timeline_object.hit_ms <= current_ms:
            global_data.camera.h_scale = timeline_object.cam_h_scale
            should_advance = True

        if hasattr(timeline_object, 'cam_v_scale') and timeline_object.hit_ms <= current_ms:
            global_data.camera.v_scale = timeline_object.cam_v_scale
            should_advance = True

        if hasattr(timeline_object, 'cam_rotation') and timeline_object.hit_ms <= current_ms:
            global_data.camera.rotation = timeline_object.cam_rotation
            should_advance = True

        if should_advance:
            self.timeline_index += 1
    '''

    def handle_judgeposition(self, current_ms: float, timeline_object: TimelineObject):
        if hasattr(timeline_object, 'judge_pos_x'):
            if timeline_object.load_ms <= current_ms <= timeline_object.hit_ms:
                duration = timeline_object.hit_ms - timeline_object.load_ms
                if duration > 0:
                    t = (current_ms - timeline_object.load_ms) / duration
                    t = max(0.0, min(1.0, t))

                    self.judge_x = (timeline_object.judge_pos_x + (timeline_object.delta_x * t)) * tex.screen_scale
                    self.judge_y = (timeline_object.judge_pos_y + (timeline_object.delta_y * t)) * tex.screen_scale
                else:
                    self.judge_x = (timeline_object.judge_pos_x + timeline_object.delta_x) * tex.screen_scale
                    self.judge_y = (timeline_object.judge_pos_y + timeline_object.delta_y) * tex.screen_scale

            if current_ms > timeline_object.hit_ms:
                self.timeline_index += 1
                if self.timeline_index < len(self.timeline):
                    next_timeline_object = self.timeline[self.timeline_index]
                    if hasattr(next_timeline_object, 'delta_x'):
                        next_timeline_object.judge_pos_x = self.judge_x / tex.screen_scale
                        next_timeline_object.judge_pos_y = self.judge_y / tex.screen_scale

    def handle_scroll_type_commands(self, current_ms: float, timeline_object: TimelineObject):
        if hasattr(timeline_object, 'bpmchange') and timeline_object.hit_ms <= current_ms:
            hit_ms = timeline_object.hit_ms
            bpmchange = timeline_object.bpmchange
            for note in chain(self.current_notes_draw, self.current_bars, self.draw_note_list, self.draw_bar_list):
                note.bpm *= bpmchange
                self.get_load_time(note)

            self.bpm *= bpmchange
            self.timeline_index += 1

        if hasattr(timeline_object, 'delay') and timeline_object.hit_ms <= current_ms:
            hit_ms = timeline_object.hit_ms
            delay = timeline_object.delay
            if self.delay_start is not None:
                logger.error('Needs fix: delay is currently active, but another delay is being activated')
            else:
                # Turn on delay visual
                self.delay_start = hit_ms
                self.delay_end = hit_ms + delay

            self.timeline_index += 1

    def handle_bpmchange(self, current_ms: float, timeline_object: TimelineObject):
        if hasattr(timeline_object, 'bpm') and timeline_object.hit_ms <= current_ms:
            self.bpm = timeline_object.bpm
            self.timeline_index += 1

    def handle_gogotime(self, current_ms: float, timeline_object: TimelineObject):
        if hasattr(timeline_object, 'gogo_time') and timeline_object.hit_ms <= current_ms:
            self.is_gogo_time = timeline_object.gogo_time
            if self.is_gogo_time:
                self.gogo_time = GogoTime(self.is_2p)
                self.chara.set_animation('gogo_start')
            else:
                self.gogo_time = None
                self.chara.set_animation('gogo_stop')
            self.timeline_index += 1

    def handle_timeline(self, current_ms: float):
        if not self.timeline or self.timeline_index >= len(self.timeline):
            return
        timeline_object = self.timeline[self.timeline_index]

        self.handle_scroll_type_commands(current_ms, timeline_object)
        self.handle_bpmchange(current_ms, timeline_object)
        self.handle_judgeposition(current_ms, timeline_object)
        self.handle_gogotime(current_ms, timeline_object)

    def animation_manager(self, animation_list: list, current_time: float):
        if not animation_list:
            return

        remaining_animations = []
        for animation in animation_list:
            animation.update(current_time)
            if not animation.is_finished:
                remaining_animations.append(animation)

        animation_list[:] = remaining_animations

    def bar_manager(self, current_ms: float):
        """Manages the bars and removes if necessary
        Also sets branch conditions"""
        #Add bar to current_bars list if it is ready to be shown on screen
        if self.draw_bar_list and current_ms >= self.draw_bar_list[0].load_ms:
            bisect.insort_left(self.current_bars, self.draw_bar_list.popleft(), key=lambda x: x.load_ms)

        #If a bar is off screen, remove it
        if not self.current_bars:
            return

        bar = self.current_bars[0]
        if current_ms >= bar.unload_ms:
            self.current_bars.pop(0)
        if self.current_bars and hasattr(self.current_bars[-1], 'branch_params'):
            self.branch_condition, e_req, m_req = self.current_bars[-1].branch_params.split(',')
            delattr(self.current_bars[-1], 'branch_params')
            e_req = float(e_req)
            m_req = float(m_req)
            logger.info(f'branch condition measures started with conditions {self.branch_condition}, {e_req}, {m_req}, {self.current_bars[-1].hit_ms}')
            if not self.is_branch:
                self.is_branch = True
                if self.branch_condition == 'r':
                    end_time = self.branch_m[0].bars[0].load_ms
                    self.curr_branch_reqs = [e_req, m_req, end_time, 1]
                elif self.branch_condition == 'p':
                    start_time = self.current_bars[0].hit_ms if self.current_bars else self.current_bars[-1].hit_ms
                    branch_start_time = self.branch_m[0].bars[0].load_ms

                    note_lists = [
                        self.current_notes_draw,
                        self.branch_n[0].draw_notes if self.branch_n else [],
                        self.branch_e[0].draw_notes if self.branch_e else [],
                        self.branch_m[0].draw_notes if self.branch_m else [],
                        self.draw_note_list if self.draw_note_list else []
                    ]

                    seen_notes = set()
                    for notes in note_lists:
                        for note in notes:
                            if note.type <= 4 and start_time <= note.hit_ms < branch_start_time:
                                seen_notes.add(note)

                    self.curr_branch_reqs = [e_req, m_req, branch_start_time, max(len(seen_notes), 1)]
    def play_note_manager(self, current_ms: float, background: Optional[Background]):
        """Manages the play_notes and removes if necessary"""
        if self.don_notes and self.don_notes[0].hit_ms + Player.TIMING_BAD < current_ms:
            self.combo = 0
            if background is not None:
                if self.is_2p:
                    background.add_chibi(True, 2)
                else:
                    background.add_chibi(True, 1)
            self.bad_count += 1
            self.input_log[self.don_notes[0].index] = 'BAD'
            if self.gauge is not None:
                self.gauge.add_bad()
            self.don_notes.popleft()
            if self.is_branch and self.branch_condition == 'p':
                self.branch_condition_count -= 1

        if self.kat_notes and self.kat_notes[0].hit_ms + Player.TIMING_BAD < current_ms:
            self.combo = 0
            if background is not None:
                if self.is_2p:
                    background.add_chibi(True, 2)
                else:
                    background.add_chibi(True, 1)
            self.bad_count += 1
            self.input_log[self.kat_notes[0].index] = 'BAD'
            if self.gauge is not None:
                self.gauge.add_bad()
            self.kat_notes.popleft()
            if self.is_branch and self.branch_condition == 'p':
                self.branch_condition_count -= 1

        if not self.other_notes:
            return

        note = self.other_notes[0]
        if (note.hit_ms <= current_ms):
            if note.type == NoteType.ROLL_HEAD or note.type == NoteType.ROLL_HEAD_L:
                self.is_drumroll = True
            elif note.type == NoteType.BALLOON_HEAD or note.type == NoteType.KUSUDAMA:
                self.is_balloon = True
            elif note.type == NoteType.TAIL:
                self.other_notes.popleft()
                self.is_drumroll = False
                self.is_balloon = False
                self.curr_balloon_count = 0
                self.curr_drumroll_count = 0
                return
            tail = self.other_notes[1]
            if tail.hit_ms <= current_ms:
                self.other_notes.popleft()
                self.other_notes.popleft()
                self.is_drumroll = False
                self.is_balloon = False
                self.curr_balloon_count = 0
                self.curr_drumroll_count = 0

    def draw_note_manager(self, current_ms: float):
        """Manages the draw_notes and removes if necessary"""
        if self.draw_note_list and current_ms >= self.draw_note_list[0].load_ms:
            current_note = self.draw_note_list.popleft()
            if 5 <= current_note.type <= 7:
                bisect.insort_left(self.current_notes_draw, current_note, key=lambda x: x.index)
                tail_note = next((note for note in self.draw_note_list if note.type == NoteType.TAIL))
                bisect.insort_left(self.current_notes_draw, tail_note, key=lambda x: x.index)
                self.draw_note_list.remove(tail_note)
            else:
                bisect.insort_left(self.current_notes_draw, current_note, key=lambda x: x.index)

        if not self.current_notes_draw:
            return

        if isinstance(self.current_notes_draw[0], Drumroll):
            self.current_notes_draw[0].color = min(255, self.current_notes_draw[0].color + 1)

        note = self.current_notes_draw[0]
        if note.type in {NoteType.ROLL_HEAD, NoteType.ROLL_HEAD_L, NoteType.BALLOON_HEAD, NoteType.KUSUDAMA} and len(self.current_notes_draw) > 1:
            note = self.current_notes_draw[1]
        if current_ms >= note.unload_ms:
            self.current_notes_draw.pop(0)

    def note_manager(self, current_ms: float, background: Optional[Background]):
        self.bar_manager(current_ms)
        self.play_note_manager(current_ms, background)
        self.draw_note_manager(current_ms)

    def note_correct(self, note: Note, current_time: float):
        """Removes a note from the appropriate separated list"""
        if note.type in {NoteType.DON, NoteType.DON_L} and self.don_notes and self.don_notes[0] == note:
            self.don_notes.popleft()
        elif note.type in {NoteType.KAT, NoteType.KAT_L} and self.kat_notes and self.kat_notes[0] == note:
            self.kat_notes.popleft()
        elif note.type not in {NoteType.DON, NoteType.DON_L, NoteType.KAT, NoteType.KAT_L} and self.other_notes and self.other_notes[0] == note:
            self.other_notes.popleft()

        index = note.index
        if note.type == NoteType.BALLOON_HEAD:
            if self.other_notes:
                self.other_notes.popleft()

        if note.type < 7:
            self.combo += 1
            if self.combo % 10 == 0:
                self.chara.set_animation('10_combo')
            if self.combo % 100 == 0:
                self.combo_announce = ComboAnnounce(self.combo, current_time, self.player_num, self.is_2p)
            if self.combo > self.max_combo:
                self.max_combo = self.combo
            if self.combo % 100 == 0 and self.score_method == ScoreMethod.GEN3:
                self.score += 10000
                self.base_score_list.append(ScoreCounterAnimation(self.player_num, 10000, self.is_2p))

        if note.type != NoteType.KUSUDAMA:
            is_big = note.type == NoteType.DON_L or note.type == NoteType.KAT_L or note.type == NoteType.BALLOON_HEAD
            is_balloon = note.type == NoteType.BALLOON_HEAD
            self.draw_arc_list.append(NoteArc(note.type, current_time, PlayerNum(self.is_2p + 1), is_big, is_balloon, start_x=self.judge_x, start_y=self.judge_y))

        if note in self.current_notes_draw:
            index = self.current_notes_draw.index(note)
            self.current_notes_draw.pop(index)

    def check_drumroll(self, drum_type: DrumType, background: Optional[Background], current_time: float):
        """Checks if a note has been hit during a drumroll"""
        self.draw_arc_list.append(NoteArc(drum_type, current_time, PlayerNum(self.is_2p + 1), drum_type == 3 or drum_type == 4, False))
        self.curr_drumroll_count += 1
        self.total_drumroll += 1
        if self.is_branch and self.branch_condition == 'r':
            self.branch_condition_count += 1
        if background is not None:
            background.add_renda()
        self.score += 100
        self.base_score_list.append(ScoreCounterAnimation(self.player_num, 100, self.is_2p))
        if not self.current_notes_draw:
            return
        if not isinstance(self.current_notes_draw[0], Drumroll):
            return
        self.current_notes_draw[0].color = max(0, 255 - (self.curr_drumroll_count * 10))

    def check_balloon(self, drum_type: DrumType, note: Balloon, current_time: float):
        """Checks if the player has popped a balloon"""
        if drum_type != DrumType.DON:
            return
        if note.is_kusudama:
            self.check_kusudama(note, current_time)
            return
        if self.balloon_anim is None:
            self.balloon_anim = BalloonAnimation(current_time, note.count, self.player_num, self.is_2p)
        self.curr_balloon_count += 1
        self.total_drumroll += 1
        self.score += 100
        self.base_score_list.append(ScoreCounterAnimation(self.player_num, 100, self.is_2p))
        if self.curr_balloon_count == note.count:
            self.is_balloon = False
            note.popped = True
            self.balloon_anim.update(current_time, self.curr_balloon_count, note.popped)
            audio.play_sound('balloon_pop', 'hitsound')
            self.note_correct(note, current_time)
            self.curr_balloon_count = 0

    def check_kusudama(self, note: Balloon, current_time: float):
        """Checks if the player has popped a kusudama"""
        if self.kusudama_anim is None:
            self.kusudama_anim = KusudamaAnimation(note.count)
        self.curr_balloon_count += 1
        self.total_drumroll += 1
        self.score += 100
        self.base_score_list.append(ScoreCounterAnimation(self.player_num, 100, self.is_2p))
        if self.curr_balloon_count == note.count:
            audio.play_sound('kusudama_pop', 'hitsound')
            self.is_balloon = False
            note.popped = True
            self.kusudama_anim.update(current_time, note.popped)
            self.curr_balloon_count = 0

    def check_note(self, ms_from_start: float, drum_type: DrumType, current_time: float, background: Optional[Background]):
        """Checks if the player has hit a note"""
        if len(self.don_notes) == 0 and len(self.kat_notes) == 0 and len(self.other_notes) == 0:
            return

        if self.difficulty < Difficulty.NORMAL:
            good_window_ms = Player.TIMING_GOOD_EASY
            ok_window_ms = Player.TIMING_OK_EASY
            bad_window_ms = Player.TIMING_BAD_EASY
        else:
            good_window_ms = Player.TIMING_GOOD
            ok_window_ms = Player.TIMING_OK
            bad_window_ms = Player.TIMING_BAD

        if self.score_method == ScoreMethod.GEN3:
            self.base_score = self.score_init
            if 9 < self.combo and self.combo < 30:
                self.base_score = math.floor(self.score_init + 1 * self.score_diff)
            elif 29 < self.combo and self.combo < 50:
                self.base_score = math.floor(self.score_init + 2 * self.score_diff)
            elif 49 < self.combo and self.combo < 100:
                self.base_score = math.floor(self.score_init + 4 * self.score_diff)
            elif 99 < self.combo:
                self.base_score = math.floor(self.score_init + 8 * self.score_diff)

        curr_note = self.other_notes[0] if self.other_notes else None
        if self.is_drumroll:
            self.check_drumroll(drum_type, background, current_time)
        elif self.is_balloon:
            if not isinstance(curr_note, Balloon):
                return
            self.check_balloon(drum_type, curr_note, current_time)
        else:
            self.curr_drumroll_count = 0

            if drum_type == DrumType.DON:
                if not self.don_notes:
                    return
                curr_note = self.don_notes[0]
            else:
                if not self.kat_notes:
                    return
                curr_note = self.kat_notes[0]

            #If the note is too far away, stop checking
            if ms_from_start > (curr_note.hit_ms + bad_window_ms):
                return

            big = curr_note.type == NoteType.DON_L or curr_note.type == NoteType.KAT_L
            if (curr_note.hit_ms - good_window_ms) <= ms_from_start <= (curr_note.hit_ms + good_window_ms):
                self.draw_judge_list.append(Judgment(Judgments.GOOD, big, self.is_2p))
                self.lane_hit_effect = LaneHitEffect(Judgments.GOOD, self.is_2p)
                self.good_count += 1
                self.score += self.base_score
                self.base_score_list.append(ScoreCounterAnimation(self.player_num, self.base_score, self.is_2p))
                self.input_log[curr_note.index] = 'GOOD'
                self.note_correct(curr_note, current_time)
                if self.gauge is not None:
                    self.gauge.add_good()
                if self.is_branch and self.branch_condition == 'p':
                    self.branch_condition_count += 1
                if background is not None:
                    if self.is_2p:
                        background.add_chibi(False, 2)
                    else:
                        background.add_chibi(False, 1)

            elif (curr_note.hit_ms - ok_window_ms) <= ms_from_start <= (curr_note.hit_ms + ok_window_ms):
                self.draw_judge_list.append(Judgment(Judgments.OK, big, self.is_2p))
                self.ok_count += 1
                self.score += 10 * math.floor(self.base_score / 2 / 10)
                self.base_score_list.append(ScoreCounterAnimation(self.player_num, 10 * math.floor(self.base_score / 2 / 10), self.is_2p))
                self.input_log[curr_note.index] = 'OK'
                self.note_correct(curr_note, current_time)
                if self.gauge is not None:
                    self.gauge.add_ok()
                if self.is_branch and self.branch_condition == 'p':
                    self.branch_condition_count += 0.5
                if background is not None:
                    if self.is_2p:
                        background.add_chibi(False, 2)
                    else:
                        background.add_chibi(False, 1)

            elif (curr_note.hit_ms - bad_window_ms) <= ms_from_start <= (curr_note.hit_ms + bad_window_ms):
                self.input_log[curr_note.index] = 'BAD'
                self.draw_judge_list.append(Judgment(Judgments.BAD, big, self.is_2p))
                self.bad_count += 1
                self.combo = 0
                if drum_type == DrumType.DON:
                    note = self.don_notes.popleft()
                else:
                    note = self.kat_notes.popleft()
                if note in self.current_notes_draw:
                    self.current_notes_draw.remove(note)
                if self.gauge is not None:
                    self.gauge.add_bad()
                if background is not None:
                    if self.is_2p:
                        background.add_chibi(True, 2)
                    else:
                        background.add_chibi(True, 1)

    def drumroll_counter_manager(self, current_time: float):
        """Manages drumroll counter behavior"""
        if self.is_drumroll and self.curr_drumroll_count > 0 and self.drumroll_counter is None:
            self.drumroll_counter = DrumrollCounter(self.is_2p)

        if self.drumroll_counter is not None:
            if self.drumroll_counter.is_finished and not self.is_drumroll:
                self.drumroll_counter = None
            else:
                self.drumroll_counter.update(current_time, self.curr_drumroll_count)

    def balloon_manager(self, current_time: float):
        """Manages balloon and kusudama behavior"""
        if self.balloon_anim is not None:
            self.chara.set_animation('balloon_popping')
            self.balloon_anim.update(current_time, self.curr_balloon_count, not self.is_balloon)
            if self.balloon_anim.is_finished:
                if self.score_method == ScoreMethod.GEN3:
                    self.score += 5000
                    self.base_score_list.append(ScoreCounterAnimation(self.player_num, 5000, self.is_2p))
                self.balloon_anim = None
                self.chara.set_animation('balloon_pop')
        if self.kusudama_anim is not None:
            self.kusudama_anim.update(current_time, not self.is_balloon)
            self.kusudama_anim.update_count(self.curr_balloon_count)
            if self.kusudama_anim.is_finished:
                self.kusudama_anim = None

    def spawn_hit_effects(self, drum_type: DrumType, side: Side):
        self.lane_hit_effect = LaneHitEffect(drum_type, self.is_2p)
        self.draw_drum_hit_list.append(DrumHitEffect(drum_type, side, self.is_2p))

    def handle_input(self, ms_from_start: float, current_time: float, background: Optional[Background]):
        input_checks = [
            (is_l_don_pressed, DrumType.DON, Side.LEFT, f'hitsound_don_{self.player_num}p'),
            (is_r_don_pressed, DrumType.DON, Side.RIGHT, f'hitsound_don_{self.player_num}p'),
            (is_l_kat_pressed, DrumType.KAT, Side.LEFT, f'hitsound_kat_{self.player_num}p'),
            (is_r_kat_pressed, DrumType.KAT, Side.RIGHT, f'hitsound_kat_{self.player_num}p')
        ]
        for check_func, drum_type, side, sound in input_checks:
            if check_func(self.player_num):
                self.spawn_hit_effects(drum_type, side)
                audio.play_sound(sound, 'hitsound')
                self.check_note(ms_from_start, drum_type, current_time, background)

    def autoplay_manager(self, ms_from_start: float, current_time: float, background: Optional[Background]):
        """Manages autoplay behavior"""
        if not self.modifiers.auto:
            return

        # Handle drumroll and balloon hits
        if self.is_drumroll or self.is_balloon:
            if self.bpm == 0:
                subdivision_in_ms = 0
            else:
                subdivision_in_ms = ms_from_start // ((60000 * 4 / self.bpm) / 24)
            if subdivision_in_ms > self.last_subdivision:
                self.last_subdivision = subdivision_in_ms
                hit_type = DrumType.DON
                self.autoplay_hit_side = Side.RIGHT if self.autoplay_hit_side == Side.LEFT else Side.LEFT
                self.spawn_hit_effects(hit_type, self.autoplay_hit_side)
                audio.play_sound(f'hitsound_don_{self.player_num}p', 'hitsound')
                self.check_note(ms_from_start, hit_type, current_time, background)
        else:
            # Handle DON notes
            while self.don_notes and ms_from_start >= self.don_notes[0].hit_ms:
                hit_type = DrumType.DON
                self.autoplay_hit_side = Side.RIGHT if self.autoplay_hit_side == Side.LEFT else Side.LEFT
                self.spawn_hit_effects(hit_type, self.autoplay_hit_side)
                audio.play_sound(f'hitsound_don_{self.player_num}p', 'hitsound')
                self.check_note(ms_from_start, hit_type, current_time, background)

            # Handle KAT notes
            while self.kat_notes and ms_from_start >= self.kat_notes[0].hit_ms:
                hit_type = DrumType.KAT
                self.autoplay_hit_side = Side.RIGHT if self.autoplay_hit_side == Side.LEFT else Side.LEFT
                self.spawn_hit_effects(hit_type, self.autoplay_hit_side)
                audio.play_sound(f'hitsound_kat_{self.player_num}p', 'hitsound')
                self.check_note(ms_from_start, hit_type, current_time, background)

    def evaluate_branch(self, current_ms):
        """Evaluates the branch condition and updates the branch status"""
        e_req, m_req, end_time, total_notes = self.curr_branch_reqs
        if current_ms >= end_time:
            self.is_branch = False
            if self.branch_condition == 'p':
                self.branch_condition_count = max(min((self.branch_condition_count/total_notes)*100, 100), 0)
            if self.branch_indicator is not None:
                logger.info(f"Branch set to {self.branch_indicator.difficulty} based on conditions {self.branch_condition_count}, {e_req, m_req}")
            if self.branch_condition_count >= e_req and self.branch_condition_count < m_req and e_req >= 0:
                self.merge_branch_section(self.branch_e.pop(0), current_ms)
                if self.branch_indicator is not None and self.branch_indicator.difficulty != 'expert':
                    if self.branch_indicator.difficulty == 'master':
                        self.branch_indicator.level_down('expert')
                    else:
                        self.branch_indicator.level_up('expert')
                if self.branch_m:
                    self.branch_m.pop(0)
                if self.branch_n:
                    self.branch_n.pop(0)
            elif self.branch_condition_count >= m_req:
                self.merge_branch_section(self.branch_m.pop(0), current_ms)
                if self.branch_indicator is not None and self.branch_indicator.difficulty != 'master':
                    self.branch_indicator.level_up('master')
                if self.branch_n:
                    self.branch_n.pop(0)
                if self.branch_e:
                    self.branch_e.pop(0)
            else:
                self.merge_branch_section(self.branch_n.pop(0), current_ms)
                if self.branch_indicator is not None and self.branch_indicator.difficulty != 'normal':
                    self.branch_indicator.level_down('normal')
                if self.branch_m:
                    self.branch_m.pop(0)
                if self.branch_e:
                    self.branch_e.pop(0)
            self.branch_condition_count = 0

    def update(self, ms_from_start: float, current_time: float, background: Optional[Background]):
        self.note_manager(ms_from_start, background)
        self.combo_display.update(current_time, self.combo)
        self.combo_announce.update(current_time)
        self.drumroll_counter_manager(current_time)
        self.animation_manager(self.draw_judge_list, current_time)
        self.balloon_manager(current_time)
        if self.gogo_time is not None:
            self.gogo_time.update(current_time)
        if self.lane_hit_effect is not None:
            self.lane_hit_effect.update(current_time)
        self.animation_manager(self.draw_drum_hit_list, current_time)
        self.handle_timeline(ms_from_start)
        if self.delay_start is not None and self.delay_end is not None:
            # Currently, a delay is active: notes should be frozen at ms = delay_start
            # Check if it ended
            if ms_from_start >= self.delay_end:
                delay = self.delay_end - self.delay_start
                for note in chain(self.don_notes, self.kat_notes, self.other_notes, self.current_bars, self.draw_bar_list):
                    note.load_ms += delay
                self.delay_start = None
                self.delay_end = None

        # More efficient arc management
        finished_arcs = []
        for i, anim in enumerate(self.draw_arc_list):
            anim.update(current_time)
            if anim.is_finished:
                self.gauge_hit_effect.append(GaugeHitEffect(anim.note_type, anim.is_big, self.is_2p))
                finished_arcs.append(i)
        for i in reversed(finished_arcs):
            self.draw_arc_list.pop(i)

        self.animation_manager(self.gauge_hit_effect, current_time)
        self.animation_manager(self.base_score_list, current_time)
        self.score_counter.update(current_time, self.score)
        self.autoplay_manager(ms_from_start, current_time, background)
        self.handle_input(ms_from_start, current_time, background)
        self.nameplate.update(current_time)
        if self.gauge is not None:
            self.gauge.update(current_time)
        if self.judge_counter is not None:
            self.judge_counter.update(self.good_count, self.ok_count, self.bad_count, self.total_drumroll)
        if self.branch_indicator is not None:
            self.branch_indicator.update(current_time)
        if self.ending_anim is not None:
            self.ending_anim.update(current_time)

        if self.is_branch:
            self.evaluate_branch(ms_from_start)

        if self.gauge is None:
            self.chara.update(current_time, self.bpm, False, False)
        else:
            self.chara.update(current_time, self.bpm, self.gauge.is_clear, self.gauge.is_rainbow)

    def draw_drumroll(self, current_ms: float, head: Drumroll, current_eighth: int):
        """Draws a drumroll in the player's lane"""
        if hasattr(head, 'sudden_appear_ms') and hasattr(head, 'sudden_moving_ms'):
            appear_ms = head.hit_ms - head.sudden_appear_ms
            moving_start_ms = head.hit_ms - head.sudden_moving_ms
            if current_ms < appear_ms:
                return
            if current_ms < moving_start_ms:
                current_ms = moving_start_ms
        start_position = self.get_position_x(head, current_ms)
        tail = next((note for note in self.current_notes_draw[1:] if note.type == NoteType.TAIL and note.index > head.index), self.current_notes_draw[1])
        is_big = int(head.type == NoteType.ROLL_HEAD_L)
        end_position = self.get_position_x(tail, current_ms)
        length = end_position - start_position
        color = ray.Color(255, head.color, head.color, 255)
        y = tex.skin_config["notes"].y + self.get_position_y(head, current_ms) + self.judge_y
        start_position += self.judge_x
        end_position += self.judge_x
        moji_y = tex.skin_config["moji"].y
        if head.display:
            tex.draw_texture('notes', "8", frame=is_big, x=start_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y), x2=length+tex.skin_config["drumroll_width_offset"].width, color=color)
            if is_big:
                tex.draw_texture('notes', "drumroll_big_tail", x=end_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y), color=color)
            else:
                tex.draw_texture('notes', "drumroll_tail", x=end_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y), color=color)
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=start_position - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, color=color)

        tex.draw_texture('notes', 'moji_drumroll_mid', x=start_position, y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, x2=length)
        tex.draw_texture('notes', 'moji', frame=head.moji, x=start_position - (tex.textures["notes"]["moji"].width//2), y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)
        tex.draw_texture('notes', 'moji', frame=tail.moji, x=end_position - (tex.textures["notes"]["moji"].width//2), y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)

    def draw_balloon(self, current_ms: float, head: Balloon, current_eighth: int):
        """Draws a balloon in the player's lane"""
        offset = tex.skin_config["balloon_offset"].x
        if hasattr(head, 'sudden_appear_ms') and hasattr(head, 'sudden_moving_ms'):
            appear_ms = head.hit_ms - head.sudden_appear_ms
            moving_start_ms = head.hit_ms - head.sudden_moving_ms
            if current_ms < appear_ms:
                return
            if current_ms < moving_start_ms:
                current_ms = moving_start_ms
        start_position = self.get_position_x(head, current_ms)
        tail = next((note for note in self.current_notes_draw[1:] if note.type == NoteType.TAIL and note.index > head.index), self.current_notes_draw[1])
        end_position = self.get_position_x(tail, current_ms)
        pause_position = GameScreen.JUDGE_X + self.judge_x
        y = tex.skin_config["notes"].y + self.get_position_y(head, current_ms) + self.judge_y
        start_position += self.judge_x
        end_position += self.judge_x
        if current_ms >= tail.hit_ms:
            position = end_position
        elif current_ms >= head.hit_ms:
            position = pause_position
        else:
            position = start_position
        if head.display:
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=position-offset - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y))
        tex.draw_texture('notes', '10', frame=current_eighth % 2, x=position-offset+tex.textures["notes"]["10"].width - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y))

    def draw_bars(self, current_ms: float):
        """Draw bars in the player's lane"""
        if not self.current_bars:
            return

        for bar in reversed(self.current_bars):
            if not bar.display:
                continue
            x_position = self.get_position_x(bar, current_ms) + self.judge_x
            y_position = self.get_position_y(bar, current_ms) + self.judge_y
            if y_position != 0:
                angle = math.degrees(math.atan2(bar.scroll_y, bar.scroll_x))
            else:
                angle = 0
            tex.draw_texture('notes', str(bar.type), x=x_position+tex.skin_config["moji_drumroll"].x- (tex.textures["notes"]["1"].width//2), y=y_position+tex.skin_config["moji_drumroll"].y+(self.is_2p*tex.skin_config["2p_offset"].y), rotation=angle)


    def draw_notes(self, current_ms: float):
        """Draw notes in the player's lane"""
        if not self.current_notes_draw:
            return

        for note in reversed(self.current_notes_draw):
            if self.balloon_anim is not None and note == self.current_notes_draw[0]:
                continue
            if note.type == NoteType.TAIL:
                continue

            eighth_in_ms = 0 if self.bpm == 0 else (60000 * 4 / self.bpm) / 8
            current_eighth = 0
            if self.combo >= 50 and eighth_in_ms != 0:
                current_eighth = int(current_ms // eighth_in_ms)
            if hasattr(note, 'sudden_appear_ms') and hasattr(note, 'sudden_moving_ms'):
                appear_ms = note.hit_ms - note.sudden_appear_ms
                moving_start_ms = note.hit_ms - note.sudden_moving_ms

                if current_ms < appear_ms:
                    continue

                if current_ms < moving_start_ms:
                    effective_ms = moving_start_ms
                else:
                    effective_ms = current_ms
                x_position = self.get_position_x(note, effective_ms)
                y_position = self.get_position_y(note, current_ms)
            else:
                x_position = self.get_position_x(note, current_ms)
                y_position = self.get_position_y(note, current_ms)
            x_position += self.judge_x
            y_position += self.judge_y
            if isinstance(note, Drumroll):
                self.draw_drumroll(current_ms, note, current_eighth)
            elif isinstance(note, Balloon) and not note.is_kusudama:
                self.draw_balloon(current_ms, note, current_eighth)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position, y=tex.skin_config["moji"].y + y_position+(self.is_2p*tex.skin_config["2p_offset"].y))
            else:
                if note.display:
                    tex.draw_texture('notes', str(note.type), frame=current_eighth % 2, x=x_position - (tex.textures["notes"]["1"].width//2), y=y_position+tex.skin_config["notes"].y+(self.is_2p*tex.skin_config["2p_offset"].y), center=True)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position - (tex.textures["notes"]["moji"].width//2), y=tex.skin_config["moji"].y + y_position+(self.is_2p*tex.skin_config["2p_offset"].y))


    def draw_modifiers(self):
        """Shows the currently selected modifiers"""
        modifiers_to_draw = []

        if self.score_method == ScoreMethod.SHINUCHI:
            modifiers_to_draw.append('mod_shinuchi')

        # Speed modifiers
        if global_data.modifiers[self.player_num].speed >= 4:
            modifiers_to_draw.append('mod_yonbai')
        elif global_data.modifiers[self.player_num].speed >= 3:
            modifiers_to_draw.append('mod_sanbai')
        elif global_data.modifiers[self.player_num].speed > 1:
            modifiers_to_draw.append('mod_baisaku')

        # Other modifiers
        if global_data.modifiers[self.player_num].display:
            modifiers_to_draw.append('mod_doron')
        if global_data.modifiers[self.player_num].inverse:
            modifiers_to_draw.append('mod_abekobe')
        if global_data.modifiers[self.player_num].random == 2:
            modifiers_to_draw.append('mod_detarame')
        elif global_data.modifiers[self.player_num].random == 1:
            modifiers_to_draw.append('mod_kimagure')

        # Draw all modifiers in one batch
        for modifier in modifiers_to_draw:
            tex.draw_texture('lane', modifier, index=self.is_2p)

    def draw_overlays(self, mask_shader: ray.Shader):
        # Group 4: Lane covers and UI elements (batch similar textures)
        tex.draw_texture('lane', f'{self.player_num}p_lane_cover', index=self.is_2p)
        if self.is_dan:
            tex.draw_texture('lane', 'dan_lane_cover')
        tex.draw_texture('lane', 'drum', index=self.is_2p)
        if self.ending_anim is not None:
            self.ending_anim.draw()

        # Group 5: Hit effects and animations
        for anim in self.draw_drum_hit_list:
            anim.draw()
        for anim in self.draw_arc_list:
            anim.draw(mask_shader)
        for anim in self.gauge_hit_effect:
            anim.draw()

        # Group 6: UI overlays
        self.combo_display.draw()
        self.combo_announce.draw()
        if self.is_2p:
            tex.draw_texture('lane', 'lane_score_cover', index=self.is_2p, mirror='vertical')
        else:
            tex.draw_texture('lane', 'lane_score_cover', index=self.is_2p)
        tex.draw_texture('lane', f'{self.player_num}p_icon', index=self.is_2p)
        if self.is_dan:
            tex.draw_texture('lane', 'lane_difficulty', frame=6)
        else:
            tex.draw_texture('lane', 'lane_difficulty', frame=self.difficulty, index=self.is_2p)
        if self.judge_counter is not None:
            self.judge_counter.draw()

        # Group 7: Player-specific elements
        if not self.modifiers.auto:
            if self.is_2p:
                self.nameplate.draw(tex.skin_config["game_nameplate_1p"].x, tex.skin_config["game_nameplate_1p"].y)
            else:
                self.nameplate.draw(tex.skin_config["game_nameplate_2p"].x, tex.skin_config["game_nameplate_2p"].y)
        else:
            tex.draw_texture('lane', 'auto_icon', index=self.is_2p)
        self.draw_modifiers()
        self.chara.draw(y=(self.is_2p*tex.skin_config["game_2p_offset"].y))

        # Group 8: Special animations and counters
        if self.drumroll_counter is not None:
            self.drumroll_counter.draw()
        if self.balloon_anim is not None:
            self.balloon_anim.draw()
        if self.kusudama_anim is not None:
            self.kusudama_anim.draw()
        self.score_counter.draw()
        for anim in self.base_score_list:
            anim.draw()

    def draw(self, ms_from_start: float, start_ms: float, mask_shader: ray.Shader, dan_transition = None):
        # Group 1: Background and lane elements
        tex.draw_texture('lane', 'lane_background', index=self.is_2p)
        if self.branch_indicator is not None:
            self.branch_indicator.draw()
        if self.gauge is not None:
            self.gauge.draw()
        if self.lane_hit_effect is not None:
            self.lane_hit_effect.draw()
        tex.draw_texture('lane', 'lane_hit_circle', x=self.judge_x, y=self.judge_y, index=self.is_2p)

        # Group 2: judgment and hit effects
        if self.gogo_time is not None:
            self.gogo_time.draw(self.judge_x, self.judge_y)
        for anim in self.draw_judge_list:
            anim.draw(self.judge_x, self.judge_y)

        # Group 3: Notes and bars (game content)
        self.draw_bars(ms_from_start)
        self.draw_notes(ms_from_start)
        if dan_transition is not None:
            dan_transition.draw()

        self.draw_overlays(mask_shader)

class Judgment:
    """Shows the judgment of the player's hit"""
    def __init__(self, type: Judgments, big: bool, is_2p: bool):
        self.is_2p = is_2p
        self.type = type
        self.big = big
        self.is_finished = False

        self.fade_animation_1 = tex.get_animation(27, is_copy=True)
        self.fade_animation_2 = tex.get_animation(28, is_copy=True)
        self.move_animation = tex.get_animation(29, is_copy=True)
        self.texture_animation = tex.get_animation(30, is_copy=True)
        self.move_animation.start()
        self.fade_animation_2.start()
        self.fade_animation_1.start()
        self.texture_animation.start()

    def update(self, current_ms):
        animations = [self.fade_animation_1, self.fade_animation_2, self.move_animation, self.texture_animation]
        for anim in animations:
            anim.update(current_ms)

        if self.fade_animation_2.is_finished:
            self.is_finished = True

    def draw(self, judge_x: float, judge_y: float):
        y = self.move_animation.attribute
        index = self.texture_animation.attribute
        hit_fade = self.fade_animation_1.attribute
        fade = self.fade_animation_2.attribute
        if self.type == Judgments.GOOD:
            if self.big:
                tex.draw_texture('hit_effect', 'hit_effect_good_big', x=judge_x, y=judge_y, fade=fade, index=self.is_2p)
                tex.draw_texture('hit_effect', 'outer_good_big', x=judge_x, y=judge_y, frame=index, fade=hit_fade, index=self.is_2p)
            else:
                tex.draw_texture('hit_effect', 'hit_effect_good', x=judge_x, y=judge_y, fade=fade, index=self.is_2p)
                tex.draw_texture('hit_effect', 'outer_good', x=judge_x, y=judge_y, frame=index, fade=hit_fade, index=self.is_2p)
            tex.draw_texture('hit_effect', 'judge_good', y=y+judge_y, x=judge_x, fade=fade, index=self.is_2p)
        elif self.type == Judgments.OK:
            if self.big:
                tex.draw_texture('hit_effect', 'hit_effect_ok_big', x=judge_x, y=judge_y, fade=fade, index=self.is_2p)
                tex.draw_texture('hit_effect', 'outer_ok_big', x=judge_x, y=judge_y, frame=index, fade=hit_fade, index=self.is_2p)
            else:
                tex.draw_texture('hit_effect', 'hit_effect_ok', x=judge_x, y=judge_y, fade=fade, index=self.is_2p)
                tex.draw_texture('hit_effect', 'outer_ok', x=judge_x, y=judge_y, frame=index, fade=hit_fade, index=self.is_2p)
            tex.draw_texture('hit_effect', 'judge_ok', x=judge_x, y=y+judge_y, fade=fade, index=self.is_2p)
        elif self.type == Judgments.BAD:
            tex.draw_texture('hit_effect', 'judge_bad', x=judge_x, y=y+judge_y, fade=fade, index=self.is_2p)

class LaneHitEffect:
    """Display a gradient overlay when the player hits the drum"""
    def __init__(self, type: Judgments | DrumType, is_2p: bool):
        self.is_2p = is_2p
        self.type = type
        self.fade = tex.get_animation(0, is_copy=True)
        self.fade.start()
        self.is_finished = False

    def update(self, current_ms: float):
        self.fade.update(current_ms)
        if self.fade.is_finished:
            self.is_finished = True

    def draw(self):
        if self.type == Judgments.GOOD:
            tex.draw_texture('lane', 'lane_hit_effect', frame=2, index=self.is_2p, fade=self.fade.attribute)
        elif self.type == DrumType.DON:
            tex.draw_texture('lane', 'lane_hit_effect', frame=0, index=self.is_2p, fade=self.fade.attribute)
        elif self.type == DrumType.KAT:
            tex.draw_texture('lane', 'lane_hit_effect', frame=1, index=self.is_2p, fade=self.fade.attribute)

class DrumHitEffect:
    """Display the side of the drum hit"""
    def __init__(self, type: DrumType, side: Side, is_2p: bool):
        self.is_2p = is_2p
        self.type = type
        self.side = side
        self.is_finished = False
        self.fade = tex.get_animation(1, is_copy=True)
        self.fade.start()

    def update(self, current_ms: float):
        self.fade.update(current_ms)
        if self.fade.is_finished:
            self.is_finished = True

    def draw(self):
        if self.type == DrumType.DON:
            if self.side == Side.LEFT:
                tex.draw_texture('lane', 'drum_don_l', index=self.is_2p, fade=self.fade.attribute)
            elif self.side == Side.RIGHT:
                tex.draw_texture('lane', 'drum_don_r', index=self.is_2p, fade=self.fade.attribute)
        elif self.type == DrumType.KAT:
            if self.side == Side.LEFT:
                tex.draw_texture('lane', 'drum_kat_l', index=self.is_2p, fade=self.fade.attribute)
            elif self.side == Side.RIGHT:
                tex.draw_texture('lane', 'drum_kat_r', index=self.is_2p, fade=self.fade.attribute)

class GaugeHitEffect:
    """Effect when a note hits the gauge"""
    _COLOR_THRESHOLDS = [(0.70, ray.WHITE), (0.80, ray.YELLOW), (0.90, ray.ORANGE), (1.00, ray.RED)]

    def __init__(self, note_type: int, big: bool, is_2p: bool):
        self.is_2p = is_2p
        self.note_type = note_type
        self.is_big = big
        self.texture_change = tex.get_animation(2, is_copy=True)
        self.circle_fadein = tex.get_animation(31, is_copy=True)
        self.resize = tex.get_animation(32, is_copy=True)
        self.fade_out = tex.get_animation(33, is_copy=True)
        self.rotation = tex.get_animation(34, is_copy=True)
        self.texture_change.start()
        self.circle_fadein.start()
        self.resize.start()
        self.fade_out.start()
        self.rotation.start()
        self.color = ray.fade(ray.YELLOW, self.circle_fadein.attribute)
        self.is_finished = False

        self.width = tex.textures["gauge"]["hit_effect"].width

        self.texture_color = ray.WHITE
        self.dest_width = self.width * tex.screen_scale
        self.dest_height = self.width * tex.screen_scale
        self.origin = ray.Vector2(self.width//2, self.width//2)
        self.rotation_angle = 0
        self.x2_pos = -self.width
        self.y2_pos = -self.width

        # Cache for texture selection
        self.circle_texture = 'hit_effect_circle_big' if self.is_big else 'hit_effect_circle'
        self._last_resize_value = -1
        self._cached_texture_color = ray.WHITE

    def _get_texture_color_for_resize(self, resize_value):
        """Calculate texture color based on resize attribute value with caching"""
        # Use cached value if resize hasn't changed significantly
        if abs(resize_value - self._last_resize_value) < 0.01:
            return self._cached_texture_color

        self._last_resize_value = resize_value

        if resize_value >= 1.00:
            self._cached_texture_color = ray.RED
        else:
            # Use pre-defined thresholds for faster lookup
            self._cached_texture_color = ray.WHITE
            for threshold, color in self._COLOR_THRESHOLDS:
                if resize_value <= threshold:
                    self._cached_texture_color = color
                    break

        return self._cached_texture_color

    def update(self, current_ms):
        # Update all animations
        self.texture_change.update(current_ms)
        self.circle_fadein.update(current_ms)
        self.fade_out.update(current_ms)
        self.resize.update(current_ms)
        self.rotation.update(current_ms)

        # Update circle color with optimized calculation
        base_color = ray.WHITE if self.circle_fadein.is_finished else ray.YELLOW
        fade_value = min(self.fade_out.attribute, self.circle_fadein.attribute)
        self.color = ray.fade(base_color, fade_value)

        # Pre-compute drawing values only when resize changes significantly
        resize_val = self.resize.attribute
        if abs(resize_val - getattr(self, '_last_resize_calc', -1)) > 0.005:
            self._last_resize_calc = resize_val
            self.texture_color = self._get_texture_color_for_resize(resize_val)
            self.dest_width = self.width * resize_val
            self.dest_height = self.width * resize_val
            self.origin = ray.Vector2(self.dest_width / 2, self.dest_height / 2)
            self.x2_pos = -self.width + (self.width * resize_val)
            self.y2_pos = -self.width + (self.width * resize_val)

        self.rotation_angle = self.rotation.attribute * 100

        # Check if finished
        if self.fade_out.is_finished:
            self.is_finished = True

    def draw(self):
        fade_value = self.fade_out.attribute

        # Main hit effect texture
        tex.draw_texture('gauge', 'hit_effect',
                        frame=self.texture_change.attribute,
                        x2=self.x2_pos,
                        index=self.is_2p,
                        y2=self.y2_pos,
                        color=ray.fade(self.texture_color, fade_value),
                        origin=self.origin,
                        rotation=self.rotation_angle,
                        center=True)

        # Note type texture
        pos_data = tex.skin_config["gauge_hit_effect_note"]
        tex.draw_texture('notes', str(self.note_type),
            x=pos_data.x, y=pos_data.y+(self.is_2p*(pos_data.height)),
                        fade=fade_value)

        # Circle effect texture (use cached texture name)
        tex.draw_texture('gauge', self.circle_texture, color=self.color, index=self.is_2p)

class NoteArc:
    """Note arcing from the player to the gauge"""
    def __init__(self, note_type: int, current_ms: float, player_num: PlayerNum, big: bool, is_balloon: bool, start_x: float = 0, start_y: float = 0):
        self.note_type = note_type
        self.is_big = big
        self.is_balloon = is_balloon
        self.arc_points = 100
        self.arc_duration = 22
        self.current_progress = 0
        self.create_ms = current_ms
        self.player_num = player_num

        self.explosion_point_index = 0
        self.points_per_explosion = 5

        curve_height = 425 * tex.screen_scale
        self.start_x, self.start_y = start_x + (350 * tex.screen_scale), start_y + (192 * tex.screen_scale)
        self.end_x, self.end_y = 1158 * tex.screen_scale, 101 * tex.screen_scale
        if self.player_num == PlayerNum.P2:
            self.start_y += (176 * tex.screen_scale)
            self.end_y += (372 * tex.screen_scale)
        self.explosion_x = self.start_x
        self.explosion_y = self.start_y

        if self.player_num == PlayerNum.P1:
            # Control point influences the curve shape
            self.control_x = (self.start_x + self.end_x) // 2
            self.control_y = min(self.start_y, self.end_y) - curve_height  # Arc upward
        else:
            self.control_x = (self.start_x + self.end_x) // 2
            self.control_y = max(self.start_y, self.end_y) + curve_height  # Arc downward

        self.x_i = self.start_x
        self.y_i = self.start_y
        self.is_finished = False
        self.arc_points_cache = []
        for i in range(self.arc_points + 1):
            t = i / self.arc_points
            t_inv = 1.0 - t
            x = int(t_inv * t_inv * self.start_x + 2 * t_inv * t * self.control_x + t * t * self.end_x)
            y = int(t_inv * t_inv * self.start_y + 2 * t_inv * t * self.control_y + t * t * self.end_y)
            self.arc_points_cache.append((x, y))

        self.explosion_x, self.explosion_y = self.arc_points_cache[0]
        self.explosion_anim = tex.get_animation(22)
        self.explosion_anim.start()

    def update(self, current_ms: float):
        ms_since_call = (current_ms - self.create_ms) / 16.67
        ms_since_call = max(0, min(ms_since_call, self.arc_duration))

        self.current_progress = ms_since_call / self.arc_duration
        if self.current_progress >= 1.0:
            self.is_finished = True
            self.x_i, self.y_i = self.arc_points_cache[-1]
            return

        point_index = int(self.current_progress * self.arc_points)
        if point_index < len(self.arc_points_cache):
            self.x_i, self.y_i = self.arc_points_cache[point_index]
        else:
            self.x_i, self.y_i = self.arc_points_cache[-1]

        self.explosion_anim.update(current_ms)
        if self.explosion_anim.is_finished:
            self.explosion_point_index = min(
                self.explosion_point_index + self.points_per_explosion,
                len(self.arc_points_cache) - 1
            )

            self.explosion_x, self.explosion_y = self.arc_points_cache[self.explosion_point_index*4]
            self.explosion_anim.restart()

    def draw(self, mask_shader: ray.Shader):
        if self.is_balloon:
            rainbow = tex.textures['balloon']['rainbow']
            if self.player_num == PlayerNum.P2:
                rainbow_height = -rainbow.height
            else:
                rainbow_height = rainbow.height
            trail_length_ratio = 0.5
            trail_start_progress = max(0, self.current_progress - trail_length_ratio)
            trail_end_progress = self.current_progress

            if trail_end_progress > trail_start_progress:
                crop_start_x = int(trail_start_progress * rainbow.width)
                crop_end_x = int(trail_end_progress * rainbow.width)
                crop_width = crop_end_x - crop_start_x

                if crop_width > 0:
                    src = ray.Rectangle(crop_start_x, 0, crop_width, rainbow_height)
                    mirror = 'vertical' if self.player_num == PlayerNum.P2 else ''
                    y = (435 * tex.screen_scale) if self.player_num == PlayerNum.P2 else 0
                    ray.begin_shader_mode(mask_shader)
                    tex.draw_texture('balloon', 'rainbow_mask', src=src, x=crop_start_x, x2=-rainbow.width + crop_width, mirror=mirror, y=y)
                    ray.end_shader_mode()

                    tex.draw_texture('balloon', 'explosion', x=self.explosion_x, y=self.explosion_y-(30 * tex.screen_scale), frame=self.explosion_anim.attribute)
        '''
        elif self.is_big:
            tex.draw_texture('hit_effect', 'explosion', x=self.explosion_x, y=self.explosion_y-30, frame=self.explosion_anim.attribute)
        '''
        tex.draw_texture('notes', str(self.note_type), x=self.x_i, y=self.y_i)

class DrumrollCounter:
    """Displays a drumroll counter, stays alive until is_drumroll is false"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.is_finished = False
        self.drumroll_count = 0
        self.fade_animation = tex.get_animation(8)
        self.fade_animation.start()
        self.stretch_animation = tex.get_animation(9)

    def update_count(self, count: int):
        if self.drumroll_count != count:
            self.drumroll_count = count
            self.stretch_animation.start()
            self.fade_animation.start()

    def update(self, current_ms: float, drumroll_count: int):
        self.stretch_animation.update(current_ms)
        self.fade_animation.update(current_ms)

        if drumroll_count != 0:
            self.update_count(drumroll_count)
        if self.fade_animation.is_finished:
            self.is_finished = True

    def draw(self):
        color = ray.fade(ray.WHITE, self.fade_animation.attribute)
        tex.draw_texture('drumroll_counter', 'bubble', color=color, index=self.is_2p)
        counter = str(self.drumroll_count)
        total_width = len(counter) * tex.skin_config["drumroll_counter_margin"].x
        for i, digit in enumerate(counter):
            tex.draw_texture('drumroll_counter', 'counter', color=color, index=self.is_2p, frame=int(digit), x=-(total_width//2)+(i*tex.skin_config["drumroll_counter_margin"].x), y=-self.stretch_animation.attribute, y2=self.stretch_animation.attribute)

class BalloonAnimation:
    """Draws a Balloon"""
    def __init__(self, current_ms: float, balloon_total: int, player_num: PlayerNum, is_2p: bool):
        self.player_num = player_num
        self.is_2p = is_2p
        self.create_ms = current_ms
        self.is_finished = False
        self.total_duration = 83.33
        self.color = ray.fade(ray.WHITE, 1.0)
        self.balloon_count = 0
        self.balloon_total = balloon_total
        self.is_popped = False
        self.stretch_animation = tex.get_animation(6)
        self.fade_animation = tex.get_animation(7)
        self.fade_animation.start()

    def update_count(self, balloon_count: int):
        if self.balloon_count != balloon_count:
            self.balloon_count = balloon_count
            self.stretch_animation.start()

    def update(self, current_ms: float, balloon_count: int, is_popped: bool):
        self.update_count(balloon_count)
        self.stretch_animation.update(current_ms)
        self.is_popped = is_popped

        elapsed_time = current_ms - self.create_ms
        if self.is_popped:
            self.fade_animation.update(current_ms)
            self.color = ray.fade(ray.WHITE, self.fade_animation.attribute)
        else:
            self.total_duration = elapsed_time + 166
            self.fade_animation.delay = self.total_duration - 166
        if self.fade_animation.is_finished:
            self.is_finished = True

    def draw(self):
        if self.is_popped:
            tex.draw_texture('balloon', 'pop', frame=7, color=self.color, y=self.is_2p*tex.skin_config["2p_offset"].y)
        elif self.balloon_count >= 1:
            balloon_index = min(6, (self.balloon_count - 1) * 6 // self.balloon_total)
            tex.draw_texture('balloon', 'pop', frame=balloon_index, color=self.color, index=self.player_num-1, y=self.is_2p*tex.skin_config["2p_offset"].y)
        if self.balloon_count > 0:
            tex.draw_texture('balloon', 'bubble', y=self.is_2p*(410 * tex.screen_scale), mirror='vertical' if self.is_2p else '')
            counter = str(max(0, self.balloon_total - self.balloon_count + 1))
            total_width = len(counter) * tex.skin_config["drumroll_counter_margin"].x
            for i, digit in enumerate(counter):
                tex.draw_texture('balloon', 'counter', frame=int(digit), color=self.color, x=-(total_width // 2) + (i * tex.skin_config["drumroll_counter_margin"].x), y=-self.stretch_animation.attribute+(self.is_2p*435), y2=self.stretch_animation.attribute)

class KusudamaAnimation:
    """Draws a Kusudama"""
    def __init__(self, balloon_total: int):
        self.balloon_total = balloon_total
        self.move_down = tex.get_animation(11)
        self.move_up = tex.get_animation(12)
        self.renda_move_up = tex.get_animation(13)
        self.renda_move_down = tex.get_animation(18)
        self.renda_fade_in = tex.get_animation(14)
        self.renda_fade_out = tex.get_animation(20)
        self.stretch_animation = tex.get_animation(15)
        self.breathing = tex.get_animation(16)
        self.renda_breathe = tex.get_animation(17)
        self.open = tex.get_animation(19)
        self.fade_out = tex.get_animation(21)
        self.balloon_count = 0
        self.is_popped = False
        self.is_finished = False
        self.move_down.start()
        self.move_up.start()
        self.renda_move_up.start()
        self.renda_move_down.start()
        self.renda_fade_in.start()

        self.open.reset()
        self.renda_fade_out.reset()
        self.fade_out.reset()

    def update_count(self, balloon_count: int):
        if self.balloon_count != balloon_count:
            self.balloon_count = balloon_count
            self.stretch_animation.start()
            self.breathing.start()

    def update(self, current_ms, is_popped: bool):
        if is_popped and not self.is_popped:
            self.is_popped = True
            self.open.start()
            self.renda_fade_out.start()
            self.fade_out.start()
        self.move_down.update(current_ms)
        self.move_up.update(current_ms)
        self.renda_move_up.update(current_ms)
        self.renda_move_down.update(current_ms)
        self.renda_fade_in.update(current_ms)
        self.renda_fade_out.update(current_ms)
        self.fade_out.update(current_ms)
        self.stretch_animation.update(current_ms)
        self.breathing.update(current_ms)
        self.renda_breathe.update(current_ms)
        self.open.update(current_ms)
        self.is_finished = self.fade_out.is_finished
    def draw(self):
        y = self.move_down.attribute - self.move_up.attribute
        renda_y = -self.renda_move_up.attribute + self.renda_move_down.attribute + self.renda_breathe.attribute
        tex.draw_texture('kusudama', 'kusudama', frame=self.open.attribute, y=y, scale=self.breathing.attribute, center=True, fade=self.fade_out.attribute)
        tex.draw_texture('kusudama', 'renda', y=renda_y, fade=min(self.renda_fade_in.attribute, self.renda_fade_out.attribute))

        if self.move_up.is_finished and not self.is_popped:
            counter = str(max(0, self.balloon_total - self.balloon_count))
            if counter == '0':
                return
            total_width = len(counter) * tex.skin_config["kusudama_counter_margin"].x
            for i, digit in enumerate(counter):
                tex.draw_texture('kusudama', 'counter', frame=int(digit), x=-(total_width // 2) + (i * tex.skin_config["kusudama_counter_margin"].x), y=-self.stretch_animation.attribute, y2=self.stretch_animation.attribute)

class Combo:
    """Displays the current combo"""
    def __init__(self, combo: int, current_ms: float, is_2p: bool):
        self.combo = combo
        self.is_2p = is_2p
        self.stretch_animation = tex.get_animation(5, is_copy=True)
        self.color = [ray.fade(ray.WHITE, 1), ray.fade(ray.WHITE, 1), ray.fade(ray.WHITE, 1)]
        self.glimmer_dict = {0: 0, 1: 0, 2: 0}
        self.total_time = 250
        self.cycle_time = self.total_time * 2
        self.start_times = [
                    current_ms,
                    current_ms + (2 / 3) * self.cycle_time,
                    current_ms + (4 / 3) * self.cycle_time
                ]

    def update_count(self, combo: int):
        if self.combo != combo:
            self.combo = combo
            self.stretch_animation.start()

    def update(self, current_ms: float, combo: int):
        self.update_count(combo)
        self.stretch_animation.update(current_ms)

        for i in range(3):
            elapsed_time = current_ms - self.start_times[i]
            if elapsed_time > self.cycle_time:
                cycles_completed = elapsed_time // self.cycle_time
                self.start_times[i] += cycles_completed * self.cycle_time
                elapsed_time = current_ms - self.start_times[i]
            if elapsed_time <= self.total_time:
                self.glimmer_dict[i] = -int(elapsed_time // 16.67)
                fade_start_time = self.total_time - 164
                if elapsed_time >= fade_start_time:
                    fade = 1 - (elapsed_time - fade_start_time) / 164
                else:
                    fade = 1
            else:
                self.glimmer_dict[i] = 0
                fade = 0
            self.color[i] = ray.fade(ray.WHITE, fade)

    def draw(self):
        if self.combo < 3:
            return

        # Cache string conversion
        if self.combo != getattr(self, '_cached_combo_value', -1):
            self._cached_combo_value = self.combo
            self._cached_combo_str = str(self.combo)
        counter = self._cached_combo_str

        if self.combo < 100:
            margin = tex.skin_config["combo_margin"].x
            total_width = len(counter) * margin
            tex.draw_texture('combo', 'combo', index=self.is_2p)
            for i, digit in enumerate(counter):
                tex.draw_texture('combo', 'counter', frame=int(digit), x=-(total_width // 2) + (i * margin), y=-self.stretch_animation.attribute, y2=self.stretch_animation.attribute, index=self.is_2p)
        else:
            margin = tex.skin_config["combo_margin"].y
            total_width = len(counter) * margin
            tex.draw_texture('combo', 'combo_100', index=self.is_2p)
            for i, digit in enumerate(counter):
                tex.draw_texture('combo', 'counter_100', frame=int(digit), x=-(total_width // 2) + (i * margin), y=-self.stretch_animation.attribute, y2=self.stretch_animation.attribute, index=self.is_2p)
            glimmer_positions = [(225 * tex.screen_scale, 210 * tex.screen_scale), (200 * tex.screen_scale, 230 * tex.screen_scale), (250 * tex.screen_scale, 230 * tex.screen_scale)]
            for j, (x, y) in enumerate(glimmer_positions):
                for i in range(3):
                    tex.draw_texture('combo', 'gleam', x=x+(i*tex.skin_config["combo_margin"].x), y=y+self.glimmer_dict[j] + (self.is_2p*tex.skin_config["2p_offset"].y), color=self.color[j])

class ScoreCounter:
    """Displays the total score"""
    def __init__(self, score: int, is_2p: bool):
        self.is_2p = is_2p
        self.score = score
        self.stretch = tex.get_animation(4, is_copy=True)

    def update_count(self, score: int):
        if self.score != score:
            self.score = score
            self.stretch.start()

    def update(self, current_ms: float, score: int):
        self.update_count(score)
        if self.score > 0:
            self.stretch.update(current_ms)

    def draw(self):
        # Cache string conversion
        if self.score != getattr(self, '_cached_score_value', -1):
            self._cached_score_value = self.score
            self._cached_score_str = str(self.score)
        counter = self._cached_score_str

        x, y = 150 * tex.screen_scale, (185 * tex.screen_scale) + (self.is_2p*310*tex.screen_scale)
        margin = tex.skin_config["score_counter_margin"].x
        total_width = len(counter) * margin
        start_x = x - total_width
        for i, digit in enumerate(counter):
            tex.draw_texture('lane', 'score_number', frame=int(digit), x=start_x + (i * margin), y=y - self.stretch.attribute, y2=self.stretch.attribute)

class ScoreCounterAnimation:
    """Displays the score init being added to the total score"""
    def __init__(self, player_num: PlayerNum, counter: int, is_2p: bool):
        self.is_2p = is_2p
        self.counter = counter
        self.direction = -1 if self.is_2p else 1
        self.fade_animation_1 = tex.get_animation(35, is_copy=True)
        self.move_animation_1 = tex.get_animation(36, is_copy=True)
        self.fade_animation_2 = tex.get_animation(37, is_copy=True)
        self.move_animation_2 = tex.get_animation(38, is_copy=True)
        self.move_animation_3 = tex.get_animation(39, is_copy=True)
        self.move_animation_4 = tex.get_animation(40, is_copy=True)
        self.fade_animation_1.start()
        self.move_animation_1.start()
        self.fade_animation_2.start()
        self.move_animation_2.start()
        self.move_animation_3.start()
        self.move_animation_4.start()

        if player_num == PlayerNum.P2:
            self.base_color = ray.Color(84, 250, 238, 255)
        else:
            self.base_color = ray.Color(254, 102, 0, 255)
        self.color = ray.fade(self.base_color, 1.0)
        self.is_finished = False

        # Cache string and layout calculations
        self.counter_str = str(counter)
        self.margin = tex.skin_config["score_counter_margin"].x
        self.total_width = len(self.counter_str) * self.margin
        self.y_pos_list = []

    def update(self, current_ms: float):
        self.fade_animation_1.update(current_ms)
        self.move_animation_1.update(current_ms)
        self.move_animation_2.update(current_ms)
        self.move_animation_3.update(current_ms)
        self.move_animation_4.update(current_ms)
        self.fade_animation_2.update(current_ms)

        fade_value = self.fade_animation_2.attribute if self.fade_animation_1.is_finished else self.fade_animation_1.attribute
        self.color = ray.fade(self.base_color, fade_value)

        if self.fade_animation_2.is_finished:
            self.is_finished = True

        # Cache y positions
        self.y_pos_list = [self.move_animation_4.attribute + i*5 for i in range(1, len(self.counter_str)+1)]

    def draw(self):
        x = self.move_animation_2.attribute if self.move_animation_1.is_finished else self.move_animation_1.attribute
        if x == 0:
            return

        start_x = x - self.total_width

        for i, digit in enumerate(self.counter_str):
            if self.move_animation_3.is_finished:
                y = self.y_pos_list[i]
            elif self.move_animation_2.is_finished:
                y = self.move_animation_3.attribute
            else:
                y = 148 * tex.screen_scale

            y_offset = y * self.direction

            tex.draw_texture('lane', 'score_number',
                           frame=int(digit),
                           x=start_x + (i * self.margin),
                           y=y_offset + (self.is_2p * 680 * tex.screen_scale),
                           color=self.color)

class SongInfo:
    """Displays the song name and genre"""
    def __init__(self, song_name: str, genre: int):
        self.song_name = song_name
        self.genre = genre
        self.song_title = OutlinedText(song_name, tex.skin_config["song_info"].font_size, ray.WHITE, outline_thickness=5)
        self.fade = tex.get_animation(3)

    def update(self, current_ms: float):
        self.fade.update(current_ms)

    def draw(self):
        tex.draw_texture('song_info', 'song_num', fade=self.fade.attribute, frame=global_data.songs_played % 4)

        text_x = tex.skin_config["song_info"].x - self.song_title.texture.width
        text_y = tex.skin_config["song_info"].y - self.song_title.texture.height//2
        self.song_title.draw(outline_color=ray.BLACK, x=text_x, y=text_y, color=ray.fade(ray.WHITE, 1 - self.fade.attribute))

        if self.genre < 9:
            tex.draw_texture('song_info', 'genre', fade=1 - self.fade.attribute, frame=self.genre)

class ResultTransition:
    """Displays the result transition animation"""
    def __init__(self, player_num: PlayerNum):
        self.player_num = player_num
        self.move = global_tex.get_animation(5)
        self.move.reset()
        self.is_finished = False
        self.is_started = False

    def start(self):
        self.move.start()

    def update(self, current_ms: float):
        self.move.update(current_ms)
        self.is_started = self.move.is_started
        self.is_finished = self.move.is_finished

    def draw(self):
        x = 0
        while x < tex.screen_width:
            tex_height = global_tex.textures['result_transition']['1p_shutter_footer'].height
            if self.player_num == PlayerNum.TWO_PLAYER:
                global_tex.draw_texture('result_transition', '1p_shutter', frame=0, x=x, y=-tex.screen_height + self.move.attribute)
                global_tex.draw_texture('result_transition', '2p_shutter', frame=0, x=x, y=tex.screen_height - self.move.attribute)
                global_tex.draw_texture('result_transition', '1p_shutter_footer', x=x, y=-(tex_height*3) + self.move.attribute)
                global_tex.draw_texture('result_transition', '2p_shutter_footer', x=x, y=tex.screen_height + (tex_height*2) - self.move.attribute)
            else:
                global_tex.draw_texture('result_transition', f'{self.player_num}p_shutter', frame=0, x=x, y=-tex.screen_height + self.move.attribute)
                global_tex.draw_texture('result_transition', f'{self.player_num}p_shutter', frame=0, x=x, y=tex.screen_height - self.move.attribute)
                global_tex.draw_texture('result_transition', f'{self.player_num}p_shutter_footer', x=x, y=-(tex_height*3) + self.move.attribute)
                global_tex.draw_texture('result_transition', f'{self.player_num}p_shutter_footer', x=x, y=tex.screen_height + (tex_height*2) - self.move.attribute)
            x += tex.screen_width // 5

class GogoTime:
    """Displays the Gogo Time fire and fireworks"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.explosion_anim = tex.get_animation(23, is_copy=True)
        self.fire_resize = tex.get_animation(24, is_copy=True)
        self.fire_change = tex.get_animation(25, is_copy=True)

        self.explosion_anim.start()
        self.fire_resize.start()
        self.fire_change.start()
    def update(self, current_time_ms: float):
        self.explosion_anim.update(current_time_ms)
        self.fire_resize.update(current_time_ms)
        self.fire_change.update(current_time_ms)

    def draw(self, judge_x: float, judge_y: float):
        tex.draw_texture('gogo_time', 'fire', scale=self.fire_resize.attribute, frame=self.fire_change.attribute, fade=0.5, center=True, x=judge_x, y=judge_y, index=self.is_2p)
        if not self.explosion_anim.is_finished and not self.is_2p:
            for i in range(5):
                tex.draw_texture('gogo_time', 'explosion', frame=self.explosion_anim.attribute, index=i)

class ComboAnnounce:
    """Displays the combo every 100 combos"""
    def __init__(self, combo: int, current_time_ms: float, player_num: PlayerNum, is_2p: bool):
        self.player_num = player_num
        self.is_2p = is_2p
        self.combo = combo
        self.wait = current_time_ms
        self.fade = tex.get_animation(65)
        self.fade.start()
        self.is_finished = False
        self.audio_played = False

    def update(self, current_time_ms: float):
        if current_time_ms >= self.wait + 1666.67 and not self.is_finished:
            self.fade.start()
            self.is_finished = True

        self.fade.update(current_time_ms)
        if not self.audio_played and self.combo >= 100:
            audio.play_sound(f'combo_{self.combo}_{self.player_num}p', 'voice')
            self.audio_played = True

    def draw(self):
        if self.combo == 0:
            return
        if not self.is_finished:
            fade = 1 - self.fade.attribute
        else:
            fade = self.fade.attribute
        tex.draw_texture('combo', f'announce_bg_{self.player_num}p', fade=fade, index=self.is_2p)

        if self.combo >= 1000:
            thousands = self.combo // 1000
            remaining_hundreds = (self.combo % 1000) // 100
            thousands_offset = -110
            hundreds_offset = 20
            if self.combo % 1000 == 0:
                tex.draw_texture('combo', 'announce_number', frame=thousands-1, x=-23 * tex.screen_scale, fade=fade, index=self.is_2p)
                tex.draw_texture('combo', 'announce_add', frame=0, x=435 * tex.screen_scale, fade=fade, index=self.is_2p)
            else:
                if thousands <= 5:
                    tex.draw_texture('combo', 'announce_add', frame=thousands, x=429 * tex.screen_scale + thousands_offset, fade=fade, index=self.is_2p)
                if remaining_hundreds > 0:
                    tex.draw_texture('combo', 'announce_number', frame=remaining_hundreds-1, x=hundreds_offset, fade=fade, index=self.is_2p)
            text_offset = -30 * tex.screen_scale
        else:
            text_offset = 0
            tex.draw_texture('combo', 'announce_number', frame=self.combo // 100 - 1, x=0, fade=fade, index=self.is_2p)
        tex.draw_texture('combo', 'announce_text', x=-text_offset/2, fade=fade, index=self.is_2p)

class BranchIndicator:
    """Displays the branch difficulty and changes"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.difficulty = 'normal'
        self.diff_2 = self.difficulty
        self.diff_down = tex.get_animation(41)
        self.diff_up = tex.get_animation(42)
        self.diff_fade = tex.get_animation(43)
        self.level_fade = tex.get_animation(44)
        self.level_scale = tex.get_animation(45)
        self.direction = 1
    def update(self, current_time_ms):
        self.diff_down.update(current_time_ms)
        self.diff_up.update(current_time_ms)
        self.diff_fade.update(current_time_ms)
        self.level_fade.update(current_time_ms)
        self.level_scale.update(current_time_ms)
    def level_up(self, difficulty):
        self.diff_2 = self.difficulty
        self.difficulty = difficulty
        self.diff_down.start()
        self.diff_up.start()
        self.diff_fade.start()
        self.level_fade.start()
        self.level_scale.start()
        self.direction = 1
    def level_down(self, difficulty):
        self.diff_2 = self.difficulty
        self.difficulty = difficulty
        self.diff_down.start()
        self.diff_up.start()
        self.diff_fade.start()
        self.level_fade.start()
        self.level_scale.start()
        self.direction = -1
    def draw(self):
        if self.difficulty == 'expert':
            tex.draw_texture('branch', 'expert_bg', fade=min(0.5, 1 - self.diff_fade.attribute), index=self.is_2p)
        if self.difficulty == 'master':
            tex.draw_texture('branch', 'master_bg', fade=min(0.5, 1 - self.diff_fade.attribute), index=self.is_2p)
        if self.direction == -1:
            tex.draw_texture('branch', 'level_down', scale=self.level_scale.attribute, fade=self.level_fade.attribute, center=True, index=self.is_2p)
        else:
            tex.draw_texture('branch', 'level_up', scale=self.level_scale.attribute, fade=self.level_fade.attribute, center=True, index=self.is_2p)
        tex.draw_texture('branch', self.diff_2, y=(self.diff_down.attribute - self.diff_up.attribute) * self.direction, fade=self.diff_fade.attribute, index=self.is_2p)
        tex.draw_texture('branch', self.difficulty, y=(self.diff_up.attribute * (self.direction*-1)) - ((70 * tex.screen_scale)*self.direction*-1), fade=1 - self.diff_fade.attribute, index=self.is_2p)

class FailAnimation:
    """Animates the fail effect"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.bachio_fade_in = tex.get_animation(46)
        self.bachio_texture_change = tex.get_animation(47)
        self.bachio_fall = tex.get_animation(48)
        self.bachio_move_out = tex.get_animation(49)
        self.bachio_boom_fade_in = tex.get_animation(50)
        self.bachio_boom_scale = tex.get_animation(51)
        self.bachio_up = tex.get_animation(52)
        self.bachio_down = tex.get_animation(53)
        self.text_fade_in = tex.get_animation(54)
        self.text_fade_in.start()
        self.bachio_fade_in.start()
        self.bachio_texture_change.start()
        self.bachio_fall.start()
        self.bachio_move_out.start()
        self.bachio_boom_fade_in.start()
        self.bachio_boom_scale.start()
        self.bachio_up.start()
        self.bachio_down.start()
        self.name = 'in'
        self.frame = self.bachio_texture_change.attribute
        audio.play_sound('fail', 'sound')
    def update(self, current_time_ms: float):
        self.bachio_fade_in.update(current_time_ms)
        self.bachio_texture_change.update(current_time_ms)
        self.bachio_fall.update(current_time_ms)
        self.bachio_move_out.update(current_time_ms)
        self.bachio_boom_fade_in.update(current_time_ms)
        self.bachio_boom_scale.update(current_time_ms)
        self.bachio_up.update(current_time_ms)
        self.bachio_down.update(current_time_ms)
        self.text_fade_in.update(current_time_ms)
        if self.bachio_texture_change.is_finished:
            self.name = 'fall'
            self.frame = self.bachio_fall.attribute
        else:
            self.frame = self.bachio_texture_change.attribute
    def draw(self):
        tex.draw_texture('ending_anim', 'fail', fade=self.text_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_l_' + self.name, x=-self.bachio_move_out.attribute - (self.bachio_up.attribute/2), y=self.bachio_down.attribute - self.bachio_up.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_r_' + self.name, x=self.bachio_move_out.attribute + (self.bachio_up.attribute/2), y=self.bachio_down.attribute - self.bachio_up.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_boom', index=0, fade=self.bachio_boom_fade_in.attribute, center=True, scale=self.bachio_boom_scale.attribute, y=(self.is_2p*tex.skin_config["2p_offset"].y))
        tex.draw_texture('ending_anim', 'bachio_boom', index=1, fade=self.bachio_boom_fade_in.attribute, center=True, scale=self.bachio_boom_scale.attribute, y=(self.is_2p*tex.skin_config["2p_offset"].y))

class ClearAnimation:
    """Animates the clear effect"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.bachio_fade_in = tex.get_animation(46)
        self.bachio_fade_in.start()
        self.bachio_texture_change = tex.get_animation(47)
        self.bachio_texture_change.start()
        self.bachio_out = tex.get_animation(55)
        self.bachio_out.start()
        self.bachio_move_out = tex.get_animation(66)
        self.bachio_move_out.start()
        self.clear_separate_fade_in = [Animation.create_fade(100, initial_opacity=0.0, final_opacity=1.0, delay=i*50) for i in range(5)]
        for fade in self.clear_separate_fade_in:
            fade.start()
        self.clear_separate_stretch = [Animation.create_text_stretch(200, delay=i*50) for i in range(5)]
        for stretch in self.clear_separate_stretch:
            stretch.start()
        self.clear_highlight_fade_in = tex.get_animation(56)
        self.clear_highlight_fade_in.start()
        self.draw_clear_full = False
        self.name = 'in'
        self.frame = 0
        audio.play_sound('clear', 'sound')

    def update(self, current_time_ms: float):
        self.bachio_fade_in.update(current_time_ms)
        self.bachio_texture_change.update(current_time_ms)
        self.bachio_out.update(current_time_ms)
        self.bachio_move_out.update(current_time_ms)
        self.clear_highlight_fade_in.update(current_time_ms)
        if self.clear_highlight_fade_in.attribute == 1.0:
            self.draw_clear_full = True
        for fade in self.clear_separate_fade_in:
            fade.update(current_time_ms)
        for stretch in self.clear_separate_stretch:
            stretch.update(current_time_ms)
        if self.bachio_texture_change.is_finished:
            self.name = 'out'
            self.frame = self.bachio_out.attribute
        else:
            self.frame = self.bachio_texture_change.attribute
    def draw(self):
        if self.draw_clear_full:
            tex.draw_texture('ending_anim', 'clear', index=self.is_2p)
        else:
            for i in range(4, -1, -1):
                tex.draw_texture('ending_anim', 'clear_separated', frame=i, fade=self.clear_separate_fade_in[i].attribute, x=i*60 * tex.screen_scale, y=-self.clear_separate_stretch[i].attribute, y2=self.clear_separate_stretch[i].attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'clear_highlight', fade=self.clear_highlight_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_l_' + self.name, x=-self.bachio_move_out.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_r_' + self.name, x=self.bachio_move_out.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)

class FCAnimation:
    """Animates the full combo effect"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.bachio_fade_in = tex.get_animation(46)
        self.bachio_fade_in.start()
        self.bachio_texture_change = tex.get_animation(47)
        self.bachio_texture_change.start()
        self.bachio_out = tex.get_animation(55)
        self.bachio_out.start()
        self.bachio_move_out = tex.get_animation(49)
        self.bachio_move_out.start()
        self.clear_separate_fade_in = [Animation.create_fade(100, initial_opacity=0.0, final_opacity=1.0, delay=i*50) for i in range(5)]
        for fade in self.clear_separate_fade_in:
            fade.start()
        self.clear_separate_stretch = [Animation.create_text_stretch(200, delay=i*50) for i in range(5)]
        for stretch in self.clear_separate_stretch:
            stretch.start()
        self.clear_highlight_fade_in = tex.get_animation(56)
        self.clear_highlight_fade_in.start()
        self.fc_highlight_up = tex.get_animation(57)
        self.fc_highlight_up.start()
        self.fc_highlight_fade_out = tex.get_animation(58)
        self.bachio_move_out_2 = tex.get_animation(59)
        self.bachio_move_up = tex.get_animation(60)
        self.fan_fade_in = tex.get_animation(61)
        self.fan_texture_change = tex.get_animation(62)
        self.draw_clear_full = False
        self.name = 'in'
        self.frame = 0
        audio.play_sound('full_combo', 'sound')

    def update(self, current_time_ms: float):
        self.bachio_fade_in.update(current_time_ms)
        self.bachio_texture_change.update(current_time_ms)
        self.bachio_out.update(current_time_ms)
        self.bachio_move_out.update(current_time_ms)
        self.clear_highlight_fade_in.update(current_time_ms)
        self.fc_highlight_up.update(current_time_ms)
        self.fc_highlight_fade_out.update(current_time_ms)
        self.bachio_move_out_2.update(current_time_ms)
        self.bachio_move_up.update(current_time_ms)
        self.fan_fade_in.update(current_time_ms)
        self.fan_texture_change.update(current_time_ms)
        if self.fc_highlight_up.is_finished and not self.fc_highlight_fade_out.is_started:
            self.fc_highlight_fade_out.start()
            self.bachio_move_out_2.start()
            self.bachio_move_up.start()
            self.fan_fade_in.start()
            self.fan_texture_change.start()
            audio.play_sound('full_combo_voice', 'voice')
        if self.clear_highlight_fade_in.attribute == 1.0:
            self.draw_clear_full = True
        for fade in self.clear_separate_fade_in:
            fade.update(current_time_ms)
        for stretch in self.clear_separate_stretch:
            stretch.update(current_time_ms)
        if self.bachio_texture_change.is_finished:
            self.name = 'out'
            self.frame = self.bachio_out.attribute
        else:
            self.frame = self.bachio_texture_change.attribute
    def draw(self):
        if self.draw_clear_full:
            tex.draw_texture('ending_anim', 'full_combo_overlay', y=-self.fc_highlight_up.attribute, fade=0.5, index=self.is_2p)
            tex.draw_texture('ending_anim', 'full_combo', y=-self.fc_highlight_up.attribute, index=self.is_2p)
            tex.draw_texture('ending_anim', 'full_combo_highlight', y=-self.fc_highlight_up.attribute, fade=self.fc_highlight_fade_out.attribute, index=self.is_2p)
            tex.draw_texture('ending_anim', 'fan_l', frame=self.fan_texture_change.attribute, fade=self.fan_fade_in.attribute, index=self.is_2p)
            tex.draw_texture('ending_anim', 'fan_r', frame=self.fan_texture_change.attribute, fade=self.fan_fade_in.attribute, index=self.is_2p)
        else:
            for i in range(4, -1, -1):
                tex.draw_texture('ending_anim', 'clear_separated', frame=i, fade=self.clear_separate_fade_in[i].attribute, x=i*60 * tex.screen_scale, y=-self.clear_separate_stretch[i].attribute, y2=self.clear_separate_stretch[i].attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'clear_highlight', fade=self.clear_highlight_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_l_' + self.name, x=(-self.bachio_move_out.attribute - self.bachio_move_out_2.attribute)*1.15, y=-self.bachio_move_up.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('ending_anim', 'bachio_r_' + self.name, x=(self.bachio_move_out.attribute + self.bachio_move_out_2.attribute)*1.15, y=-self.bachio_move_up.attribute, frame=self.frame, fade=self.bachio_fade_in.attribute, index=self.is_2p)

class JudgeCounter:
    """Counts the number of good, ok, bad, and drumroll notes in real time"""
    def __init__(self):
        self.good = 0
        self.ok = 0
        self.bad = 0
        self.drumrolls = 0
        self.orange = ray.Color(253, 161, 0, 255)
        self.white = ray.WHITE
    def update(self, good: int, ok: int, bad: int, drumrolls: int):
        self.good = good
        self.ok = ok
        self.bad = bad
        self.drumrolls = drumrolls
    def draw_counter(self, counter: float, x: float, y: float, margin: float, color: ray.Color):
        counter_str = str(rounded(counter))
        counter_len = len(counter_str)
        for i, digit in enumerate(counter_str):
            tex.draw_texture('judge_counter', 'counter', frame=int(digit), x=x - (counter_len - i) * margin, y=y, color=color)
    def draw(self):
        tex.draw_texture('judge_counter', 'bg')
        tex.draw_texture('judge_counter', 'total_percent')
        tex.draw_texture('judge_counter', 'judgments')
        tex.draw_texture('judge_counter', 'drumrolls')

        for i in range(4):
            tex.draw_texture('judge_counter', 'percent', index=i, color=self.orange)

        total_notes = self.good + self.ok + self.bad
        if total_notes == 0:
            total_notes = 1
        margin = tex.skin_config["judge_counter_margin"].x
        self.draw_counter(self.good / total_notes * 100, tex.skin_config["judge_counter_1"].x, tex.skin_config["judge_counter_1"].y, margin, self.orange)
        self.draw_counter(self.ok / total_notes * 100, tex.skin_config["judge_counter_1"].x, tex.skin_config["judge_counter_3"].y, margin, self.orange)
        self.draw_counter(self.bad / total_notes * 100, tex.skin_config["judge_counter_1"].x, tex.skin_config["judge_counter_4"].x, margin, self.orange)
        self.draw_counter((self.good + self.ok) / total_notes * 100, tex.skin_config["judge_counter_3"].x, tex.skin_config["judge_counter_4"].y, margin, self.orange)
        self.draw_counter(self.good, tex.skin_config["judge_counter_2"].x, tex.skin_config["judge_counter_1"].y, margin, self.white)
        self.draw_counter(self.ok, tex.skin_config["judge_counter_2"].x, tex.skin_config["judge_counter_3"].y, margin, self.white)
        self.draw_counter(self.bad, tex.skin_config["judge_counter_2"].x, tex.skin_config["judge_counter_4"].x, margin, self.white)
        self.draw_counter(self.drumrolls, tex.skin_config["judge_counter_2"].x, tex.skin_config["judge_counter_4"].width, margin, self.white)

class Gauge:
    """The player's gauge"""
    def __init__(self, player_num: PlayerNum, difficulty: int, level: int, total_notes: int, is_2p: bool):
        self.is_2p = is_2p
        self.player_num = player_num
        self.string_diff = "_hard"
        self.gauge_length = 0
        self.previous_length = 0
        self.total_notes = total_notes
        self.difficulty = min(Difficulty.ONI, difficulty)
        self.clear_start = [52, 60, 69, 69]
        self.gauge_max = 87
        self.level = min(10, level)
        self.tamashii_fire_change = tex.get_animation(25)
        if self.difficulty == Difficulty.HARD:
            self.string_diff = "_hard"
        elif self.difficulty == Difficulty.NORMAL:
            self.string_diff = "_normal"
        elif self.difficulty == Difficulty.EASY:
            self.string_diff = "_easy"
        self.is_clear = False
        self.is_rainbow = False
        self.table = [
            [
                {"clear_rate": 36.0, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 38.0, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 38.0, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 44.0, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 44.0, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
            ],
            [
                {"clear_rate": 45.939, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 45.939, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 48.676, "ok_multiplier": 0.75, "bad_multiplier": -0.5},
                {"clear_rate": 49.232, "ok_multiplier": 0.75, "bad_multiplier": -0.75},
                {"clear_rate": 52.5, "ok_multiplier": 0.75, "bad_multiplier": -1.0},
                {"clear_rate": 52.5, "ok_multiplier": 0.75, "bad_multiplier": -1.0},
                {"clear_rate": 52.5, "ok_multiplier": 0.75, "bad_multiplier": -1.0},
            ],
            [
                {"clear_rate": 54.325, "ok_multiplier": 0.75, "bad_multiplier": -0.75},
                {"clear_rate": 54.325, "ok_multiplier": 0.75, "bad_multiplier": -0.75},
                {"clear_rate": 50.774, "ok_multiplier": 0.75, "bad_multiplier": -1.0},
                {"clear_rate": 48.410, "ok_multiplier": 0.75, "bad_multiplier": -1.17},
                {"clear_rate": 47.246, "ok_multiplier": 0.75, "bad_multiplier": -1.25},
                {"clear_rate": 48.120, "ok_multiplier": 0.75, "bad_multiplier": -1.25},
                {"clear_rate": 48.120, "ok_multiplier": 0.75, "bad_multiplier": -1.25},
                {"clear_rate": 48.120, "ok_multiplier": 0.75, "bad_multiplier": -1.25},
            ],
            [
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.603, "ok_multiplier": 0.5, "bad_multiplier": -1.6},
                {"clear_rate": 56.0, "ok_multiplier": 0.5, "bad_multiplier": -2.0},
                {"clear_rate": 61.428, "ok_multiplier": 0.5, "bad_multiplier": -2.0},
                {"clear_rate": 61.428, "ok_multiplier": 0.5, "bad_multiplier": -2.0},
            ]
        ]
        self.gauge_update_anim = tex.get_animation(10)
        self.rainbow_fade_in = None
        self.rainbow_animation = tex.get_animation(64)

    def add_good(self):
        """Adds a good note to the gauge"""
        self.gauge_update_anim.start()
        self.previous_length = int(self.gauge_length)
        self.gauge_length += (1 / self.total_notes) * (100 * (self.clear_start[self.difficulty] / self.table[self.difficulty][self.level-1]["clear_rate"]))
        if self.gauge_length > self.gauge_max:
            self.gauge_length = self.gauge_max

    def add_ok(self):
        """Adds an ok note to the gauge"""
        self.gauge_update_anim.start()
        self.previous_length = int(self.gauge_length)
        self.gauge_length += ((1 * self.table[self.difficulty][self.level-1]["ok_multiplier"]) / self.total_notes) * (100 * (self.clear_start[self.difficulty] / self.table[self.difficulty][self.level-1]["clear_rate"]))
        if self.gauge_length > self.gauge_max:
            self.gauge_length = self.gauge_max

    def add_bad(self):
        """Adds a bad note to the gauge"""
        self.previous_length = int(self.gauge_length)
        self.gauge_length += ((1 * self.table[self.difficulty][self.level-1]["bad_multiplier"]) / self.total_notes) * (100 * (self.clear_start[self.difficulty] / self.table[self.difficulty][self.level-1]["clear_rate"]))
        if self.gauge_length < 0:
            self.gauge_length = 0

    def update(self, current_ms: float):
        self.is_clear = self.gauge_length > self.clear_start[min(self.difficulty, Difficulty.HARD)]-1
        self.is_rainbow = self.gauge_length == self.gauge_max
        if self.gauge_length == self.gauge_max and self.rainbow_fade_in is None:
            self.rainbow_fade_in = tex.get_animation(63)
            self.rainbow_fade_in.start()
        self.gauge_update_anim.update(current_ms)
        self.tamashii_fire_change.update(current_ms)

        if self.rainbow_fade_in is not None:
            self.rainbow_fade_in.update(current_ms)

        self.rainbow_animation.update(current_ms)

    def draw(self):
        mirror = 'vertical' if self.is_2p else ''
        tex.draw_texture('gauge', 'border' + self.string_diff, index=self.is_2p, mirror=mirror)
        tex.draw_texture('gauge', f'{self.player_num}p_unfilled' + self.string_diff, index=self.is_2p, mirror=mirror)
        gauge_length = int(self.gauge_length)
        clear_point = self.clear_start[self.difficulty]
        bar_width = tex.textures["gauge"][f"{self.player_num}p_bar"].width
        tex.draw_texture('gauge', f'{self.player_num}p_bar', x2=min(gauge_length*bar_width, (clear_point - 1)*bar_width)-bar_width, index=self.is_2p)
        if gauge_length >= clear_point - 1:
            tex.draw_texture('gauge', 'bar_clear_transition', x=(clear_point - 1)*bar_width, index=self.is_2p, mirror=mirror)
        if gauge_length > clear_point:
            tex.draw_texture('gauge', 'bar_clear_top', x=(clear_point) * bar_width, x2=(gauge_length-clear_point)*bar_width, index=self.is_2p, mirror=mirror)
            tex.draw_texture('gauge', 'bar_clear_bottom', x=(clear_point) * bar_width, x2=(gauge_length-clear_point)*bar_width, index=self.is_2p)

        # Rainbow effect for full gauge
        if gauge_length == self.gauge_max and self.rainbow_fade_in is not None:
            if 0 < self.rainbow_animation.attribute < 8:
                tex.draw_texture('gauge', 'rainbow' + self.string_diff, frame=self.rainbow_animation.attribute-1, fade=self.rainbow_fade_in.attribute, index=self.is_2p, mirror=mirror)
            tex.draw_texture('gauge', 'rainbow' + self.string_diff, frame=self.rainbow_animation.attribute, fade=self.rainbow_fade_in.attribute, index=self.is_2p, mirror=mirror)
        if self.gauge_update_anim is not None and gauge_length <= self.gauge_max and gauge_length > self.previous_length:
            if gauge_length == self.clear_start[self.difficulty]:
                tex.draw_texture('gauge', 'bar_clear_transition_fade', x=gauge_length*bar_width, fade=self.gauge_update_anim.attribute, index=self.is_2p, mirror=mirror)
            elif gauge_length > self.clear_start[self.difficulty]:
                tex.draw_texture('gauge', 'bar_clear_fade', x=gauge_length*bar_width, fade=self.gauge_update_anim.attribute, index=self.is_2p)
            else:
                tex.draw_texture('gauge', f'{self.player_num}p_bar_fade', x=gauge_length*bar_width, fade=self.gauge_update_anim.attribute, index=self.is_2p)
        tex.draw_texture('gauge', 'overlay' + self.string_diff, fade=0.15, index=self.is_2p, mirror=mirror)

        # Draw clear status indicators
        if gauge_length >= clear_point-1:
            tex.draw_texture('gauge', 'clear', index=min(2, self.difficulty)+(self.is_2p*3))
            if self.is_rainbow:
                tex.draw_texture('gauge', 'tamashii_fire', scale=0.75, center=True, frame=self.tamashii_fire_change.attribute, index=self.is_2p)
            tex.draw_texture('gauge', 'tamashii', index=self.is_2p)
            if self.is_rainbow and self.tamashii_fire_change.attribute in (0, 1, 4, 5):
                tex.draw_texture('gauge', 'tamashii_overlay', fade=0.5, index=self.is_2p)
        else:
            tex.draw_texture('gauge', 'clear_dark', index=min(2, self.difficulty)+(self.is_2p*3))
            tex.draw_texture('gauge', 'tamashii_dark', index=self.is_2p)
