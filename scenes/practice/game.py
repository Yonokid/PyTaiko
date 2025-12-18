from collections import deque
import logging
from pathlib import Path

import pyray as ray
import copy

from libs.animation import Animation
from libs.audio import audio
from libs.background import Background
from libs.global_data import Modifiers, PlayerNum, global_data
from libs.tja import Balloon, Drumroll, Note, NoteType, TJAParser, apply_modifiers
from libs.utils import get_current_ms
from libs.texture import tex
from scenes.game import DrumHitEffect, DrumType, GameScreen, JudgeCounter, LaneHitEffect, Player, Side

logger = logging.getLogger(__name__)

class PracticeGameScreen(GameScreen):
    def on_screen_start(self):
        super().on_screen_start()
        self.background = Background(PlayerNum.P1, self.bpm, scene_preset='PRACTICE')

    def init_tja(self, song: Path):
        """Initialize the TJA file"""
        self.tja = TJAParser(song, start_delay=self.start_delay, distance=tex.screen_width - GameScreen.JUDGE_X)
        self.scrobbling_tja = TJAParser(song, start_delay=self.start_delay, distance=tex.screen_width - GameScreen.JUDGE_X)
        global_data.session_data[global_data.player_num].song_title = self.tja.metadata.title.get(global_data.config['general']['language'].lower(), self.tja.metadata.title['en'])
        if self.tja.metadata.wave.exists() and self.tja.metadata.wave.is_file() and self.song_music is None:
            self.song_music = audio.load_music_stream(self.tja.metadata.wave, 'song')
        self.player_1 = PracticePlayer(self.tja, global_data.player_num, global_data.session_data[global_data.player_num].selected_difficulty, False, global_data.modifiers[global_data.player_num])
        notes, branch_m, branch_e, branch_n = self.tja.notes_to_position(self.player_1.difficulty)
        _, self.scrobble_note_list, self.bars = apply_modifiers(notes, self.player_1.modifiers)
        self.start_ms = (get_current_ms() - self.tja.metadata.offset*1000)
        self.scrobble_index = 0
        self.scrobble_time = self.bars[self.scrobble_index].hit_ms
        self.scrobble_move = Animation.create_move(200, total_distance=0)

        self.markers = self.get_gogotime_markers(self.scrobble_note_list)

    def get_gogotime_markers(self, note_list: deque[Note | Drumroll | Balloon]):
        marker_list = []
        for i, note in enumerate(note_list):
            if i == 0 and note.gogo_time:
                marker_list.append(note.hit_ms)
            elif i > 0 and note.gogo_time:
                if not note_list[i-1].gogo_time:
                    marker_list.append(note.hit_ms)
        return marker_list

    def pause_song(self):
        self.paused = not self.paused
        self.player_1.paused = self.paused
        if self.paused:
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            self.pause_time = get_current_ms() - self.start_ms
            first_bar_time = self.bars[0].hit_ms
            nearest_bar_index = 0
            min_distance = float('inf')
            for i, bar in enumerate(self.bars):
                bar_relative_time = bar.hit_ms - first_bar_time
                distance = abs(bar_relative_time - self.current_ms)
                if distance < min_distance:
                    min_distance = distance
                    nearest_bar_index = i
            self.scrobble_index = nearest_bar_index - 1
            self.scrobble_time = self.bars[self.scrobble_index].hit_ms
        else:
            self.player_1.input_log.clear()
            resume_bar_index = max(0, self.scrobble_index)
            previous_bar_index = max(0, self.scrobble_index - global_data.config["general"]["practice_mode_bar_delay"])

            first_bar_time = self.bars[0].hit_ms
            resume_time = self.bars[resume_bar_index].hit_ms - first_bar_time + self.start_delay
            start_time = self.bars[previous_bar_index].hit_ms - first_bar_time + self.start_delay

            tja_copy = copy.deepcopy(self.scrobbling_tja)
            self.player_1.tja = tja_copy
            self.player_1.reset_chart()

            self.player_1.don_notes = deque([note for note in self.player_1.don_notes if note.hit_ms > resume_time])
            self.player_1.kat_notes = deque([note for note in self.player_1.kat_notes if note.hit_ms > resume_time])
            self.player_1.other_notes = deque([note for note in self.player_1.other_notes if note.hit_ms > resume_time])
            self.player_1.draw_note_list = deque([note for note in self.player_1.draw_note_list if note.hit_ms > resume_time])
            self.player_1.draw_bar_list = deque([note for note in self.player_1.draw_bar_list if note.hit_ms > resume_time])
            self.player_1.total_notes = len([note for note in self.player_1.play_notes if 0 < note.type < 5])

            self.pause_time = start_time
            audio.play_music_stream(self.song_music, 'music')
            audio.seek_music_stream(self.song_music, (self.pause_time - self.start_delay)/1000 - self.tja.metadata.offset)
            self.song_started = True
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
            return self.on_screen_end('PRACTICE_SELECT')

        if ray.is_key_pressed(ray.KeyboardKey.KEY_SPACE):
            self.pause_song()

        if ray.is_key_pressed(ray.KeyboardKey.KEY_LEFT) or ray.is_key_pressed(ray.KeyboardKey.KEY_RIGHT):
            audio.play_sound('kat', 'sound')

            if not self.scrobble_move.is_finished:
                self.scrobble_time = self.bars[self.scrobble_index].hit_ms

            old_index = self.scrobble_index
            if ray.is_key_pressed(ray.KeyboardKey.KEY_LEFT):
                self.scrobble_index = (self.scrobble_index - 1) if self.scrobble_index > 0 else len(self.bars) - 1
            elif ray.is_key_pressed(ray.KeyboardKey.KEY_RIGHT):
                self.scrobble_index = (self.scrobble_index + 1) % len(self.bars)

            time_difference = self.bars[self.scrobble_index].load_ms - self.bars[old_index].load_ms

            self.scrobble_move = Animation.create_move(400, total_distance=time_difference, ease_out='quadratic')
            self.scrobble_move.start()

    def update(self):
        super(GameScreen, self).update()
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
        self.scrobble_move.update(current_time)
        if self.scrobble_move.is_finished:
            self.scrobble_time = self.bars[self.scrobble_index].hit_ms
            self.scrobble_move.reset()

        self.player_1.update(self.current_ms, current_time, self.background)
        self.song_info.update(current_time)

        return self.global_keys()

    def get_position_x(self, width: int, current_ms: float, load_ms: float, pixels_per_frame: float) -> int:
        """Calculates the x-coordinate of a note based on its load time and current time"""
        if self.paused:
            time_diff = load_ms - self.scrobble_time - self.scrobble_move.attribute
        else:
            time_diff = load_ms - current_ms
        return int(width + pixels_per_frame * 0.06 * time_diff - (tex.textures["notes"]["1"].width//2))

    def get_position_y(self, current_ms: float, load_ms: float, pixels_per_frame: float, pixels_per_frame_x) -> int:
        """Calculates the y-coordinate of a note based on its load time and current time"""
        time_diff = load_ms - current_ms
        return int((pixels_per_frame * 0.06 * time_diff) + ((self.tja.distance * pixels_per_frame) / pixels_per_frame_x))

    def draw_drumroll(self, current_ms: float, head: Drumroll, current_eighth: int, index: int):
        """Draws a drumroll in the player's lane"""
        start_position = self.get_position_x(tex.screen_width, current_ms, head.load_ms, head.pixels_per_frame_x)
        tail = next((note for note in self.scrobble_note_list if note.index == index+1), self.scrobble_note_list[index+1])
        is_big = int(head.type == NoteType.ROLL_HEAD_L)
        end_position = self.get_position_x(tex.screen_width, current_ms, tail.load_ms, tail.pixels_per_frame_x)
        length = end_position - start_position
        color = ray.Color(255, head.color, head.color, 255)
        y = tex.skin_config["notes"].y
        moji_y = tex.skin_config["moji"].y
        moji_x = tex.skin_config["moji"].x
        if head.display:
            if length > 0:
                tex.draw_texture('notes', "8", frame=is_big, x=start_position+(tex.textures["notes"]["8"].width//2), y=y, x2=length+tex.skin_config["drumroll_width_offset"].width, color=color)
                if is_big:
                    tex.draw_texture('notes', "drumroll_big_tail", x=end_position+tex.textures["notes"]["drumroll_big_tail"].width//2, y=y, color=color)
                else:
                    tex.draw_texture('notes', "drumroll_tail", x=end_position+tex.textures["notes"]["drumroll_tail"].width//2, y=y, color=color)
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=start_position, y=y, color=color)

        tex.draw_texture('notes', 'moji_drumroll_mid', x=start_position + tex.skin_config["moji_drumroll"].x, y=moji_y, x2=length)
        tex.draw_texture('notes', 'moji', frame=head.moji, x=start_position - moji_x, y=moji_y)
        tex.draw_texture('notes', 'moji', frame=tail.moji, x=end_position - tex.skin_config["moji_drumroll"].width, y=moji_y)

    def draw_balloon(self, current_ms: float, head: Balloon, current_eighth: int, index: int):
        """Draws a balloon in the player's lane"""
        offset = tex.skin_config["balloon_offset"].x
        start_position = self.get_position_x(tex.screen_width, current_ms, head.load_ms, head.pixels_per_frame_x)
        tail = next((note for note in self.scrobble_note_list if note.index == index+1), self.scrobble_note_list[index+1])
        end_position = self.get_position_x(tex.screen_width, current_ms, tail.load_ms, tail.pixels_per_frame_x)
        pause_position = tex.skin_config["balloon_pause_position"].x
        if current_ms >= tail.hit_ms:
            position = end_position
        elif current_ms >= head.hit_ms:
            position = pause_position
        else:
            position = start_position
        if head.display:
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=position-offset, y=tex.skin_config["notes"].y)
        tex.draw_texture('notes', '10', frame=current_eighth % 2, x=position-offset+tex.textures["notes"]["10"].width, y=tex.skin_config["notes"].y)

    def draw_scrobble_list(self):
        bar_draws = []
        for bar in reversed(self.bars):
            if not bar.display:
                continue
            x_position = self.get_position_x(tex.screen_width, self.current_ms, bar.load_ms, bar.pixels_per_frame_x)
            y_position = self.get_position_y(self.current_ms, bar.load_ms, bar.pixels_per_frame_y, bar.pixels_per_frame_x)
            if x_position < tex.skin_config["past_judge_circle"].x or x_position > tex.screen_width:
                continue
            if hasattr(bar, 'is_branch_start'):
                frame = 1
            else:
                frame = 0
            bar_draws.append((str(bar.type), frame, x_position + tex.skin_config["moji_drumroll"].x, y_position+tex.skin_config["moji_drumroll"].y))

        for bar_type, frame, x, y in bar_draws:
            tex.draw_texture('notes', bar_type, frame=frame, x=x, y=y)

        for note in reversed(self.scrobble_note_list):
            if note.type == NoteType.TAIL:
                continue

            if isinstance(note, Drumroll):
                self.draw_drumroll(self.current_ms, note, 0, note.index)
            elif isinstance(note, Balloon) and not note.is_kusudama:
                x_position = self.get_position_x(tex.screen_width, self.current_ms, note.load_ms, note.pixels_per_frame_x)
                y_position = self.get_position_y(self.current_ms, note.load_ms, note.pixels_per_frame_y, note.pixels_per_frame_x)
                if x_position < tex.skin_config["past_judge_circle"].x or x_position > tex.screen_width:
                    continue
                self.draw_balloon(self.current_ms, note, 0, note.index)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position - tex.skin_config["moji"].x, y=tex.skin_config["moji"].y + y_position)
            else:
                x_position = self.get_position_x(tex.screen_width, self.current_ms, note.load_ms, note.pixels_per_frame_x)
                y_position = self.get_position_y(self.current_ms, note.load_ms, note.pixels_per_frame_y, note.pixels_per_frame_x)
                if x_position < tex.skin_config["past_judge_circle"].x or x_position > tex.screen_width:
                    continue

                if note.display:
                    tex.draw_texture('notes', str(note.type), x=x_position, y=y_position+tex.skin_config["notes"].y, center=True)
                color = ray.WHITE
                if note.index in self.player_1.input_log:
                    if self.player_1.input_log[note.index] == 'GOOD':
                        color = ray.Color(255, 233, 0, 255)
                    elif self.player_1.input_log[note.index] == 'BAD':
                        color = ray.Color(34, 189, 243, 255)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position - tex.skin_config["moji"].x, y=tex.skin_config["moji"].y + y_position, color=color)

    def draw(self):
        self.background.draw()
        self.player_1.draw(self.current_ms, self.start_ms, self.mask_shader)
        if self.paused:
            self.draw_scrobble_list()
        tex.draw_texture('practice', 'large_drum', index=0)
        tex.draw_texture('practice', 'large_drum', index=1)
        self.player_1.draw_overlays(self.mask_shader)
        if not self.paused:
            tex.draw_texture('practice', 'playing', index=self.player_1.player_num-1, fade=0.5)
        tex.draw_texture('practice', 'progress_bar_bg')
        if self.paused:
            tex.draw_texture('practice', 'paused', fade=0.5)
            progress = min((self.scrobble_time + self.scrobble_move.attribute - self.bars[0].hit_ms) / self.player_1.end_time, 1)
        else:
            progress = min(self.current_ms / self.player_1.end_time, 1)
        tex.draw_texture('practice', 'progress_bar', x2=progress * tex.skin_config["practice_progress_bar_width"].width)
        for marker in self.markers:
            tex.draw_texture('practice', 'gogo_marker', x=((marker - self.bars[0].hit_ms) / self.player_1.end_time) * tex.skin_config["practice_progress_bar_width"].width)
        self.draw_overlay()


class PracticePlayer(Player):
    def __init__(self, tja: TJAParser, player_num: PlayerNum, difficulty: int, is_2p: bool, modifiers: Modifiers):
        super().__init__(tja, player_num, difficulty, is_2p, modifiers)
        self.judge_counter = JudgeCounter()
        self.gauge = None
        self.paused = False

    def spawn_hit_effects(self, drum_type: DrumType, side: Side):
        self.lane_hit_effect = LaneHitEffect(drum_type, self.is_2p)
        self.draw_drum_hit_list.append(PracticeDrumHitEffect(drum_type, side, self.is_2p, player_num=self.player_num))

    def draw_overlays(self, mask_shader: ray.Shader):
        # Group 4: Lane covers and UI elements (batch similar textures)
        tex.draw_texture('lane', f'{self.player_num}p_lane_cover', index=self.is_2p)
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
        tex.draw_texture('lane', f'{self.player_num}p_icon', index=self.is_2p)
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

    def draw(self, ms_from_start: float, start_ms: float, mask_shader: ray.Shader, dan_transition = None):
        # Group 1: Background and lane elements
        tex.draw_texture('lane', 'lane_background', index=self.is_2p)
        if self.branch_indicator is not None:
            self.branch_indicator.draw()
        if self.gauge is not None:
            self.gauge.draw()
        if self.lane_hit_effect is not None:
            self.lane_hit_effect.draw()
        tex.draw_texture('lane', 'lane_hit_circle', index=self.is_2p)

        # Group 2: Judgement and hit effects
        if self.gogo_time is not None:
            self.gogo_time.draw(self.judge_x, self.judge_y)
        for anim in self.draw_judge_list:
            anim.draw(self.judge_x, self.judge_y)

        # Group 3: Notes and bars (game content)
        if not self.paused:
            self.draw_bars(ms_from_start)
            self.draw_notes(ms_from_start)

class PracticeDrumHitEffect(DrumHitEffect):
    def __init__(self, type, side, is_2p, player_num: PlayerNum = PlayerNum.P1):
        super().__init__(type, side, is_2p)
        self.player_num = player_num - 1

    def draw(self):
        if self.type == 'DON':
            if self.side == 'L':
                tex.draw_texture('lane', 'drum_don_l', index=self.is_2p, fade=self.fade.attribute)
            elif self.side == 'R':
                tex.draw_texture('lane', 'drum_don_r', index=self.is_2p, fade=self.fade.attribute)
            tex.draw_texture('practice', 'large_drum_don', index=self.player_num, fade=self.fade.attribute)
        elif self.type == 'KAT':
            if self.side == 'L':
                tex.draw_texture('lane', 'drum_kat_l', index=self.is_2p, fade=self.fade.attribute)
                tex.draw_texture('practice', 'large_drum_kat_l', index=self.player_num, fade=self.fade.attribute)
            elif self.side == 'R':
                tex.draw_texture('lane', 'drum_kat_r', index=self.is_2p, fade=self.fade.attribute)
                tex.draw_texture('practice', 'large_drum_kat_r', index=self.player_num, fade=self.fade.attribute)
