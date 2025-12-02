from collections import deque
from libs.tja2 import TJAParser2
import bisect
from enum import IntEnum
import math
import logging
from pathlib import Path

import pyray as ray

from libs.audio import audio
from libs.texture import tex
from libs.tja import calculate_base_score, NoteType
from libs.tja2 import (
    Balloon,
    Drumroll,
    Note,
)
from libs.utils import (
    get_current_ms,
    global_data,
)
from libs.video import VideoPlayer
from scenes.game import GameScreen, Player

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

class GameScreen2(GameScreen):
    def init_tja(self, song: Path):
        """Initialize the TJA file"""
        self.tja = TJAParser2(song, start_delay=self.start_delay, distance=tex.screen_width - GameScreen.JUDGE_X)
        if self.tja.metadata.bgmovie != Path() and self.tja.metadata.bgmovie.exists():
            self.movie = VideoPlayer(self.tja.metadata.bgmovie)
            self.movie.set_volume(0.0)
        else:
            self.movie = None
        global_data.session_data[global_data.player_num].song_title = self.tja.metadata.title.get(global_data.config['general']['language'].lower(), self.tja.metadata.title['en'])
        if self.tja.metadata.wave.exists() and self.tja.metadata.wave.is_file() and self.song_music is None:
            self.song_music = audio.load_music_stream(self.tja.metadata.wave, 'song')

        self.player_1 = Player2(self.tja, global_data.player_num, global_data.session_data[global_data.player_num].selected_difficulty, False, global_data.modifiers[global_data.player_num])
        self.start_ms = get_current_ms() - self.tja.metadata.offset*1000

class Player2(Player):
    def reset_chart(self):
        notes, self.branch_m, self.branch_e, self.branch_n = self.tja.notes_to_position(self.difficulty)
        self.play_notes, self.draw_note_list, self.draw_bar_list = deque(notes.play_notes), deque(notes.draw_notes), deque(notes.bars)

        self.don_notes = deque([note for note in self.play_notes if note.type in {NoteType.DON, NoteType.DON_L}])
        self.kat_notes = deque([note for note in self.play_notes if note.type in {NoteType.KAT, NoteType.KAT_L}])
        self.other_notes = deque([note for note in self.play_notes if note.type not in {NoteType.DON, NoteType.DON_L, NoteType.KAT, NoteType.KAT_L}])
        self.total_notes = len([note for note in self.play_notes if 0 < note.type < 5])
        total_notes = notes
        if self.branch_m:
            for section in self.branch_m:
                self.total_notes += len([note for note in section.play_notes if 0 < note.type < 5])
                total_notes += section
        self.base_score = calculate_base_score(total_notes)

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

        self.end_time = 0
        if self.play_notes:
            self.end_time = self.play_notes[-1].hit_ms

    def get_position_x(self, note, current_ms):
        speedx = note.bpm / 240000 * note.scroll_x * (tex.screen_width - GameScreen.JUDGE_X) * tex.screen_scale
        return GameScreen.JUDGE_X + (note.hit_ms - current_ms) * speedx


    def get_position_y(self, note, current_ms):
        speedy = note.bpm / 240000 * note.scroll_y * (tex.screen_width - GameScreen.JUDGE_Y) * tex.screen_scale
        return (note.hit_ms - current_ms) * speedy

    def bar_manager(self, current_ms: float):
        """Manages the bars and removes if necessary
        Also sets branch conditions"""
        #Add bar to current_bars list if it is ready to be shown on screen
        if self.draw_bar_list and current_ms >= self.draw_bar_list[0].hit_ms - 10000:
            self.current_bars.append(self.draw_bar_list.popleft())

    def draw_note_manager(self, current_ms: float):
        """Manages the draw_notes and removes if necessary"""
        if self.draw_note_list and current_ms >= self.draw_note_list[0].hit_ms - 10000:
            current_note = self.draw_note_list.popleft()
            if 5 <= current_note.type <= 7:
                bisect.insort_left(self.current_notes_draw, current_note, key=lambda x: x.index)
                try:
                    tail_note = next((note for note in self.draw_note_list if note.type == NoteType.TAIL))
                    bisect.insort_left(self.current_notes_draw, tail_note, key=lambda x: x.index)
                    self.draw_note_list.remove(tail_note)
                except Exception as e:
                    raise(e)
            else:
                bisect.insort_left(self.current_notes_draw, current_note, key=lambda x: x.index)

        if not self.current_notes_draw:
            return

        if isinstance(self.current_notes_draw[0], Drumroll):
            self.current_notes_draw[0].color = min(255, self.current_notes_draw[0].color + 1)

        note = self.current_notes_draw[0]
        if note.type in {NoteType.ROLL_HEAD, NoteType.ROLL_HEAD_L, NoteType.BALLOON_HEAD, NoteType.KUSUDAMA} and len(self.current_notes_draw) > 1:
            note = self.current_notes_draw[1]
        if self.get_position_x(note, current_ms) < GameScreen.JUDGE_X:
            self.current_notes_draw.pop(0)

    def draw_drumroll(self, current_ms: float, head: Drumroll, current_eighth: int):
        """Draws a drumroll in the player's lane"""
        start_position = self.get_position_x(head, current_ms)
        tail = next((note for note in self.current_notes_draw[1:] if note.type == NoteType.TAIL and note.index > head.index), self.current_notes_draw[1])
        is_big = int(head.type == NoteType.ROLL_HEAD_L)
        end_position = self.get_position_x(tail, current_ms)
        length = end_position - start_position
        color = ray.Color(255, head.color, head.color, 255)
        y = tex.skin_config["notes"].y + self.get_position_y(head, current_ms)
        moji_y = tex.skin_config["moji"].y
        moji_x = -(tex.textures["notes"]["moji"].width//2) + (tex.textures["notes"]["1"].width//2)
        if head.display:
            tex.draw_texture('notes', "8", frame=is_big, x=start_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, x2=length+tex.skin_config["drumroll_width_offset"].width, color=color)
            if is_big:
                tex.draw_texture('notes', "drumroll_big_tail", x=end_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, color=color)
            else:
                tex.draw_texture('notes', "drumroll_tail", x=end_position, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, color=color)
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=start_position - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, color=color)

        tex.draw_texture('notes', 'moji_drumroll_mid', x=start_position + tex.textures["notes"]["1"].width//2, y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y, x2=length)
        tex.draw_texture('notes', 'moji', frame=head.moji, x=start_position + moji_x, y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)
        tex.draw_texture('notes', 'moji', frame=tail.moji, x=end_position + moji_x, y=moji_y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)

    def draw_balloon(self, current_ms: float, head: Balloon, current_eighth: int):
        """Draws a balloon in the player's lane"""
        offset = tex.skin_config["balloon_offset"].x
        start_position = self.get_position_x(head, current_ms)
        tail = next((note for note in self.current_notes_draw[1:] if note.type == NoteType.TAIL and note.index > head.index), self.current_notes_draw[1])
        end_position = self.get_position_x(tail, current_ms)
        pause_position = GameScreen.JUDGE_X
        y = tex.skin_config["notes"].y + self.get_position_y(head, current_ms)
        if current_ms >= tail.hit_ms:
            position = end_position
        elif current_ms >= head.hit_ms:
            position = pause_position
        else:
            position = start_position
        if head.display:
            tex.draw_texture('notes', str(head.type), frame=current_eighth % 2, x=position-offset - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)
        tex.draw_texture('notes', '10', frame=current_eighth % 2, x=position-offset+tex.textures["notes"]["10"].width - tex.textures["notes"]["1"].width//2, y=y+(self.is_2p*tex.skin_config["2p_offset"].y)+self.judge_y)

    def draw_bars(self, current_ms: float):
        """Draw bars in the player's lane"""
        if not self.current_bars:
            return

        for bar in reversed(self.current_bars):
            if not bar.display:
                continue
            x_position = self.get_position_x(bar, current_ms)
            y_position = self.get_position_y(bar, current_ms)
            if y_position != 0:
                angle = math.degrees(math.atan2(bar.scroll_y, bar.scroll_x))
            else:
                angle = 0
            tex.draw_texture('notes', str(bar.type), x=x_position+tex.skin_config["moji_drumroll"].x- (tex.textures["notes"]["1"].width//2), y=y_position+tex.skin_config["moji_drumroll"].y+(self.is_2p*tex.skin_config["2p_offset"].y), rotation=angle)


    def draw_notes(self, current_ms: float, start_ms: float):
        """Draw notes in the player's lane"""
        if not self.current_notes_draw:
            return

        for note in reversed(self.current_notes_draw):
            if self.balloon_anim is not None and note == self.current_notes_draw[0]:
                continue
            if note.type == NoteType.TAIL:
                continue

            current_eighth = 0
            x_position = self.get_position_x(note, current_ms)
            y_position = self.get_position_y(note, current_ms)
            if isinstance(note, Drumroll):
                self.draw_drumroll(current_ms, note, current_eighth)
            elif isinstance(note, Balloon) and not note.is_kusudama:
                self.draw_balloon(current_ms, note, current_eighth)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position, y=tex.skin_config["moji"].y + y_position+(self.is_2p*tex.skin_config["2p_offset"].y))
            else:
                if note.display:
                    tex.draw_texture('notes', str(note.type), frame=current_eighth % 2, x=x_position - (tex.textures["notes"]["1"].width//2), y=y_position+tex.skin_config["notes"].y+(self.is_2p*tex.skin_config["2p_offset"].y), center=True)
                tex.draw_texture('notes', 'moji', frame=note.moji, x=x_position - (tex.textures["notes"]["moji"].width//2), y=tex.skin_config["moji"].y + y_position+(self.is_2p*tex.skin_config["2p_offset"].y))
