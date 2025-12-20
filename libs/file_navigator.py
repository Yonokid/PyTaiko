from dataclasses import dataclass
import json
import logging
from pathlib import Path
import random
from typing import Optional, Union
from libs.audio import audio
from libs.animation import Animation, MoveAnimation
from libs.global_data import Crown, Difficulty
from libs.tja import TJAParser, test_encodings
from libs.texture import tex
from libs.utils import OutlinedText, get_current_ms, global_data
from datetime import datetime, timedelta
import sqlite3
import pyray as ray

BOX_CENTER = 594 * tex.screen_scale

logger = logging.getLogger(__name__)

class BaseBox():
    OUTLINE_MAP = {
        1: ray.Color(0, 77, 104, 255),
        2: ray.Color(156, 64, 2, 255),
        3: ray.Color(84, 101, 126, 255),
        4: ray.Color(153, 4, 46, 255),
        5: ray.Color(60, 104, 0, 255),
        6: ray.Color(134, 88, 0, 255),
        7: ray.Color(79, 40, 134, 255),
        8: ray.Color(148, 24, 0, 255),
        9: ray.Color(101, 0, 82, 255),
        10: ray.Color(140, 39, 92, 255),
        11: ray.Color(151, 57, 30, 255),
        12: ray.Color(35, 123, 103, 255),
        13: ray.Color(25, 68, 137, 255),
        14: ray.Color(157, 13, 31, 255)
    }
    BACK_INDEX = 17
    DEFAULT_INDEX = 9
    DIFFICULTY_SORT_INDEX = 14
    """Base class for all box types in the song select screen."""
    def __init__(self, name: str, texture_index: int):
        self.text_name = name
        self.texture_index = texture_index
        self.position = float('inf')
        self.start_position: float = -1
        self.target_position: float = -1
        self.open_anim = Animation.create_move(233, total_distance=150*tex.screen_scale, delay=50)
        self.open_fade = Animation.create_fade(200, initial_opacity=0, final_opacity=1.0)
        self.move = None
        self.is_open = False
        self.text_loaded = False
        self.wait = 0

    def __lt__(self, other):
        return self.position < other.position

    def __le__(self, other):
        return self.position <= other.position

    def __gt__(self, other):
        return self.position > other.position

    def __ge__(self, other):
        return self.position >= other.position

    def __eq__(self, other):
        return self.position == other.position

    def load_text(self):
        self.name = OutlinedText(self.text_name, tex.skin_config["song_box_name"].font_size, ray.WHITE, outline_thickness=5, vertical=True)

    def move_box(self, current_time: float):
        if self.position != self.target_position and self.move is None:
            if self.position < self.target_position:
                direction = 1
            else:
                direction = -1
            if abs(self.target_position - self.position) > 250 * tex.screen_scale:
                direction *= -1
            self.move = Animation.create_move(133, total_distance=100 * direction * tex.screen_scale, ease_out='cubic')
            self.move.start()
            if self.is_open or self.target_position == BOX_CENTER:
                self.move.total_distance = int(250 * direction * tex.screen_scale)
            self.start_position = self.position
        if self.move is not None:
            self.move.update(current_time)
            self.position = self.start_position + int(self.move.attribute)
            if self.move.is_finished:
                self.position = self.target_position
                self.move = None

    def update(self, current_time: float, is_diff_select: bool):
        self.is_diff_select = is_diff_select
        self.open_anim.update(current_time)
        self.open_fade.update(current_time)

    def _draw_closed(self, x: float, y: float, outer_fade_override: float):
        tex.draw_texture('box', 'folder_texture_left', frame=self.texture_index, x=x, fade=outer_fade_override)
        offset = 1 * tex.screen_scale if self.texture_index == 3 or self.texture_index >= 9 and self.texture_index not in {10,11,12} else 0
        tex.draw_texture('box', 'folder_texture', frame=self.texture_index, x=x, x2=tex.skin_config["song_box_bg"].width, y=offset, fade=outer_fade_override)
        tex.draw_texture('box', 'folder_texture_right', frame=self.texture_index, x=x, fade=outer_fade_override)
        if self.texture_index == BaseBox.DEFAULT_INDEX:
            tex.draw_texture('box', 'genre_overlay', x=x, y=y, fade=outer_fade_override)
        elif self.texture_index == BaseBox.DIFFICULTY_SORT_INDEX:
            tex.draw_texture('box', 'diff_overlay', x=x, y=y, fade=outer_fade_override)

    def _draw_open(self, x: float, y: float, fade_override: Optional[float], is_ura: bool):
        pass

    def draw(self, x: float, y: float, is_ura: bool, inner_fade_override: Optional[float] = None, outer_fade_override: float = 1.0):
        if self.is_open and get_current_ms() >= self.wait + 83.33:
            self._draw_open(x, y, inner_fade_override, is_ura)
        else:
            self._draw_closed(x, y, outer_fade_override)

class BackBox(BaseBox):
    def __init__(self, name: str, texture_index: int):
        super().__init__(name, texture_index)
        self.yellow_box = None

    def load_text(self):
        super().load_text()
        self.text_loaded = True

    def update(self, current_time: float, is_diff_select: bool):
        super().update(current_time, is_diff_select)
        is_open_prev = self.is_open
        self.move_box(current_time)
        self.is_open = self.position == BOX_CENTER

        if self.yellow_box is not None:
            self.yellow_box.update(is_diff_select)

        if not is_open_prev and self.is_open:
            self.yellow_box = YellowBox(True)
            self.yellow_box.create_anim()
            self.wait = current_time

    def _draw_closed(self, x: float, y: float, outer_fade_override: float):
        super()._draw_closed(x, y, outer_fade_override)
        tex.draw_texture('box', 'back_text', x=x, y=y, fade=outer_fade_override)

    def _draw_open(self, x: float, y: float, fade_override: Optional[float] = None, is_ura: bool = False):
        if self.yellow_box is not None:
            self.yellow_box.draw(self, fade_override, is_ura, self.name)

class SongBox(BaseBox):
    def __init__(self, name: str, texture_index: int, tja: TJAParser, name_texture_index: Optional[int] = None):
        super().__init__(name, texture_index)
        if name_texture_index is None:
            self.name_texture_index = texture_index
        else:
            self.name_texture_index = name_texture_index
        self.scores = dict()
        self.hash = dict()
        self.score_history = None
        self.history_wait = 0
        self.tja = tja
        self.is_favorite = False
        self.yellow_box = None

    def load_text(self):
        super().load_text()
        self.text_loaded = True

    def get_scores(self):
        with sqlite3.connect(global_data.score_db) as con:
            cursor = con.cursor()
            # Batch database query for all diffs at once
            if self.tja.metadata.course_data:
                hash_values = [self.hash[diff] for diff in self.tja.metadata.course_data if diff in self.hash]
                placeholders = ','.join('?' * len(hash_values))

                batch_query = f"""
                    SELECT hash, score, good, ok, bad, drumroll, clear
                    FROM Scores
                    WHERE hash IN ({placeholders})
                """
                cursor.execute(batch_query, hash_values)

                hash_to_score = {row[0]: row[1:] for row in cursor.fetchall()}

                for diff in self.tja.metadata.course_data:
                    if diff not in self.hash:
                        continue
                    diff_hash = self.hash[diff]
                    self.scores[diff] = hash_to_score.get(diff_hash)
                self.score_history = None

    def update(self, current_time: float, is_diff_select: bool):
        super().update(current_time, is_diff_select)
        is_open_prev = self.is_open
        self.move_box(current_time)
        self.is_open = self.position == BOX_CENTER

        if self.yellow_box is not None:
            self.yellow_box.update(is_diff_select)

        if self.history_wait == 0:
            self.history_wait = current_time

        if self.score_history is None and {k: v for k, v in self.scores.items() if v is not None}:
            self.score_history = ScoreHistory(self.scores, current_time)

        if not is_open_prev and self.is_open:
            self.yellow_box = YellowBox(False, tja=self.tja)
            self.yellow_box.create_anim()
            self.wait = current_time
            if current_time >= self.history_wait + 3000:
                self.history_wait = current_time

        if self.score_history is not None:
            self.score_history.update(current_time)

    def _draw_closed(self, x: float, y: float, outer_fade_override: float):
        super()._draw_closed(x, y, outer_fade_override)

        self.name.draw(outline_color=SongBox.OUTLINE_MAP.get(self.name_texture_index, ray.Color(101, 0, 82, 255)), x=x + tex.skin_config["song_box_name"].x - int(self.name.texture.width / 2), y=y+tex.skin_config["song_box_name"].y, y2=min(self.name.texture.height, tex.skin_config["song_box_name"].height)-self.name.texture.height, fade=outer_fade_override)

        if self.tja.ex_data.new:
            tex.draw_texture('yellow_box', 'ex_data_new_song_balloon', x=x, y=y, fade=outer_fade_override)
        valid_scores = {k: v for k, v in self.scores.items() if v is not None}
        if valid_scores:
            highest_key = max(valid_scores.keys())
            score = self.scores[highest_key]
            if score and score[5] == Crown.DFC:
                tex.draw_texture('yellow_box', 'crown_dfc', x=x, y=y, frame=min(Difficulty.URA, highest_key), fade=outer_fade_override)
            elif score and score[5] == Crown.FC:
                tex.draw_texture('yellow_box', 'crown_fc', x=x, y=y, frame=min(Difficulty.URA, highest_key), fade=outer_fade_override)
            elif score and score[5] >= Crown.CLEAR:
                tex.draw_texture('yellow_box', 'crown_clear', x=x, y=y, frame=min(Difficulty.URA, highest_key), fade=outer_fade_override)

    def _draw_open(self, x: float, y: float, fade_override=None, is_ura=False):
        if self.yellow_box is not None:
            self.yellow_box.draw(self, fade_override, is_ura, self.name)

    def draw_score_history(self):
        if self.is_open and get_current_ms() >= self.wait + 83.33:
            if self.score_history is not None and get_current_ms() >= self.history_wait + 3000:
                self.score_history.draw()

class FolderBox(BaseBox):
    def __init__(self, name: str, texture_index: int, tja_count: int = 0,
        box_texture: Optional[str] = None):
        super().__init__(name, texture_index)
        self.box_texture_path = Path(box_texture) if box_texture else None
        self.is_back = self.texture_index == SongBox.BACK_INDEX
        self.tja_count = tja_count
        self.crown = dict()

    def load_text(self):
        super().load_text()
        self.hori_name = OutlinedText(self.text_name, tex.skin_config['song_hori_name'].font_size, ray.WHITE, outline_thickness=5)
        self.box_texture = ray.load_texture(str(self.box_texture_path)) if self.box_texture_path and self.box_texture_path.exists() else None
        if self.box_texture is not None:
            ray.gen_texture_mipmaps(self.box_texture)
            ray.set_texture_filter(self.box_texture, ray.TextureFilter.TEXTURE_FILTER_TRILINEAR)
        self.tja_count_text = OutlinedText(str(self.tja_count), tex.skin_config['song_tja_count'].font_size, ray.WHITE, outline_thickness=5)
        self.text_loaded = True

    def update(self, current_time: float, is_diff_select: bool):
        super().update(current_time, is_diff_select)
        is_open_prev = self.is_open
        self.move_box(current_time)
        self.is_open = self.position == BOX_CENTER

        if not is_open_prev and self.is_open:
            self.open_anim.start()
            self.open_fade.start()
            self.wait = current_time
            if self.texture_index != SongBox.BACK_INDEX and not audio.is_sound_playing('voice_enter'):
                audio.play_sound(f'genre_voice_{self.texture_index}', 'voice')
        elif not self.is_open and is_open_prev and self.texture_index != 17 and audio.is_sound_playing(f'genre_voice_{self.texture_index}'):
            audio.stop_sound(f'genre_voice_{self.texture_index}')

    def _draw_closed(self, x: float, y: float, outer_fade_override: float):
        super()._draw_closed(x, y, outer_fade_override)
        offset = 1 * tex.screen_scale if self.texture_index == 3 or self.texture_index >= 9 and self.texture_index not in {10,11,12} else 0
        tex.draw_texture('box', 'folder_clip', frame=self.texture_index, x=x - ((1 * tex.screen_scale) - offset), y=y, fade=outer_fade_override)

        self.name.draw(outline_color=SongBox.OUTLINE_MAP.get(self.texture_index, ray.Color(101, 0, 82, 255)), x=x + tex.skin_config["song_box_name"].x - int(self.name.texture.width / 2), y=y+tex.skin_config["song_box_name"].y, y2=min(self.name.texture.height, tex.skin_config["song_box_name"].height)-self.name.texture.height, fade=outer_fade_override)

        if self.crown: #Folder lamp
            highest_crown = max(self.crown)
            if self.crown[highest_crown] == Crown.DFC:
                tex.draw_texture('yellow_box', 'crown_dfc', x=x, y=y, frame=min(Difficulty.URA, highest_crown), fade=outer_fade_override)
            elif self.crown[highest_crown] == Crown.FC:
                tex.draw_texture('yellow_box', 'crown_fc', x=x, y=y, frame=min(Difficulty.URA, highest_crown), fade=outer_fade_override)
            else:
                tex.draw_texture('yellow_box', 'crown_clear', x=x, y=y, frame=min(Difficulty.URA, highest_crown), fade=outer_fade_override)

    def _draw_open(self, x: float, y: float, fade_override: Optional[float], is_ura: bool):
        color = ray.WHITE
        if fade_override is not None:
            color = ray.fade(ray.WHITE, fade_override)
        if not self.is_back and self.open_anim.attribute >= (100 * tex.screen_scale):
            tex.draw_texture('box', 'folder_top_edge', x=x, y=y - self.open_anim.attribute, color=color, mirror='horizontal', frame=self.texture_index)
            tex.draw_texture('box', 'folder_top', x=x, y=y - self.open_anim.attribute, color=color, frame=self.texture_index)
            tex.draw_texture('box', 'folder_top_edge', x=x+tex.skin_config["song_folder_top"].x, y=y - self.open_anim.attribute, color=color, frame=self.texture_index)
            dest_width = min(tex.skin_config["song_hori_name"].width, self.hori_name.texture.width)
            self.hori_name.draw(outline_color=ray.BLACK, x=(x + tex.skin_config["song_hori_name"].x) - (dest_width//2), y=y + tex.skin_config["song_hori_name"].y - self.open_anim.attribute, x2=dest_width-self.hori_name.texture.width, color=color)

        tex.draw_texture('box', 'folder_texture_left', frame=self.texture_index, x=x - self.open_anim.attribute)
        offset = 1 * tex.screen_scale if self.texture_index == 3 or self.texture_index >= 9 and self.texture_index not in {10,11,12} else 0
        tex.draw_texture('box', 'folder_texture', frame=self.texture_index, x=x - self.open_anim.attribute, y=offset, x2=(self.open_anim.attribute*2)+tex.skin_config["song_box_bg"].width)
        tex.draw_texture('box', 'folder_texture_right', frame=self.texture_index, x=x + self.open_anim.attribute)

        if self.texture_index == BaseBox.DEFAULT_INDEX:
            tex.draw_texture('box', 'genre_overlay_large', x=x, y=y, color=color)
        elif self.texture_index == BaseBox.DIFFICULTY_SORT_INDEX:
            tex.draw_texture('box', 'diff_overlay_large', x=x, y=y, color=color)

        color = ray.WHITE
        if fade_override is not None:
            color = ray.fade(ray.WHITE, fade_override)
        if self.texture_index != BaseBox.DIFFICULTY_SORT_INDEX:
            tex.draw_texture('yellow_box', 'song_count_back', color=color, fade=0.5)
            tex.draw_texture('yellow_box', 'song_count_num', color=color)
            tex.draw_texture('yellow_box', 'song_count_songs', color=color)
            dest_width = min(tex.skin_config["song_tja_count"].width, self.tja_count_text.texture.width)
            self.tja_count_text.draw(outline_color=ray.BLACK, x=tex.skin_config["song_tja_count"].x - (dest_width//2), y=tex.skin_config["song_tja_count"].y, x2=dest_width-self.tja_count_text.texture.width, color=color)
        if self.texture_index != SongBox.DEFAULT_INDEX:
            tex.draw_texture('box', 'folder_graphic', color=color, frame=self.texture_index)
            tex.draw_texture('box', 'folder_text', color=color, frame=self.texture_index)
        elif self.box_texture is not None:
            scaled_width = self.box_texture.width * tex.screen_scale
            scaled_height = self.box_texture.height * tex.screen_scale
            x = int((x + tex.skin_config["box_texture"].x) - (scaled_width // 2))
            y = int((y + tex.skin_config["box_texture"].y) - (scaled_height // 2))
            src = ray.Rectangle(0, 0, self.box_texture.width, self.box_texture.height)
            dest = ray.Rectangle(x, y, scaled_width, scaled_height)
            ray.draw_texture_pro(self.box_texture, src, dest, ray.Vector2(0, 0), 0, color)

class YellowBox:
    """A song box when it is opened."""
    def __init__(self, is_back: bool, tja: Optional[TJAParser] = None, is_dan: bool = False):
        self.is_diff_select = False
        self.is_back = is_back
        self.tja = tja
        if self.tja is not None:
            subtitle_text = self.tja.metadata.subtitle.get(global_data.config['general']['language'], '')
            font_size = tex.skin_config["yb_subtitle"].font_size if len(subtitle_text) < 30 else tex.skin_config["yb_subtitle"].font_size - int(10 * tex.screen_scale)
            self.subtitle = OutlinedText(subtitle_text, font_size, ray.WHITE, outline_thickness=5, vertical=True)
        self.is_dan = is_dan
        self.subtitle = None

        self.left_out = tex.get_animation(9)
        self.right_out = tex.get_animation(10)
        self.center_out = tex.get_animation(11)
        self.fade = tex.get_animation(12)

        self.left_out.reset()
        self.right_out.reset()
        self.center_out.reset()
        self.fade.reset()

        self.left_out_2 = tex.get_animation(13)
        self.right_out_2 = tex.get_animation(14)
        self.center_out_2 = tex.get_animation(15)
        self.top_y_out = tex.get_animation(16)
        self.center_h_out = tex.get_animation(17)
        self.fade_in = tex.get_animation(18)

        self.right_out_2.reset()
        self.top_y_out.reset()
        self.center_h_out.reset()

        self.right_x = self.right_out.attribute
        self.left_x = self.left_out.attribute
        self.center_width = self.center_out.attribute
        self.top_y = self.top_y_out.attribute
        self.center_height = self.center_h_out.attribute
        self.bottom_y = tex.textures['yellow_box']['yellow_box_bottom_right'].y[0]
        self.edge_height = tex.textures['yellow_box']['yellow_box_bottom_right'].height

    def create_anim(self):
        self.right_out_2.reset()
        self.top_y_out.reset()
        self.center_h_out.reset()
        self.left_out.start()
        self.right_out.start()
        self.center_out.start()
        self.fade.start()

    def create_anim_2(self):
        self.left_out_2.start()
        self.right_out_2.start()
        self.center_out_2.start()
        self.top_y_out.start()
        self.center_h_out.start()
        self.fade_in.start()

    def update(self, is_diff_select: bool):
        current_time = get_current_ms()
        self.left_out.update(current_time)
        self.right_out.update(current_time)
        self.center_out.update(current_time)
        self.fade.update(current_time)
        self.fade_in.update(current_time)
        self.left_out_2.update(current_time)
        self.right_out_2.update(current_time)
        self.center_out_2.update(current_time)
        self.top_y_out.update(current_time)
        self.center_h_out.update(current_time)
        if is_diff_select and not self.is_diff_select:
            self.create_anim_2()
        if self.is_diff_select:
            self.right_x = self.right_out_2.attribute
            self.left_x = self.left_out_2.attribute
            self.top_y = self.top_y_out.attribute
            self.center_width = self.center_out_2.attribute
            self.center_height = self.center_h_out.attribute
        else:
            self.right_x = self.right_out.attribute
            self.left_x = self.left_out.attribute
            self.center_width = self.center_out.attribute
            self.top_y = self.top_y_out.attribute
            self.center_height = self.center_h_out.attribute
        self.is_diff_select = is_diff_select

    def _draw_tja_data(self, song_box: SongBox, color: ray.Color, fade: float):
        if not self.tja:
            return
        offset = tex.skin_config['yb_diff_offset'].x
        for diff in self.tja.metadata.course_data:
            if diff >= Difficulty.URA:
                continue
            if diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] == Crown.DFC:
                tex.draw_texture('yellow_box', 's_crown_dfc', x=(diff*offset), color=color)
            elif diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] == Crown.FC:
                tex.draw_texture('yellow_box', 's_crown_fc', x=(diff*offset), color=color)
            elif diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] >= Crown.CLEAR:
                tex.draw_texture('yellow_box', 's_crown_clear', x=(diff*offset), color=color)
            tex.draw_texture('yellow_box', 's_crown_outline', x=(diff*offset), fade=min(fade, 0.25))

        if self.tja.ex_data.new_audio:
            tex.draw_texture('yellow_box', 'ex_data_new_audio', color=color)
        elif self.tja.ex_data.old_audio:
            tex.draw_texture('yellow_box', 'ex_data_old_audio', color=color)
        elif self.tja.ex_data.limited_time:
            tex.draw_texture('yellow_box', 'ex_data_limited_time', color=color)
        elif self.tja.ex_data.new:
            tex.draw_texture('yellow_box', 'ex_data_new_song', color=color)
        if song_box.is_favorite:
            tex.draw_texture('yellow_box', f'favorite_{global_data.player_num}p', color=color)

        for i in range(4):
            tex.draw_texture('yellow_box', 'difficulty_bar', frame=i, x=(i*offset), color=color)
            if i not in self.tja.metadata.course_data:
                tex.draw_texture('yellow_box', 'difficulty_bar_shadow', frame=i, x=(i*offset), fade=min(fade, 0.25))

        for diff in self.tja.metadata.course_data:
            if diff >= Difficulty.URA:
                continue
            for j in range(self.tja.metadata.course_data[diff].level):
                tex.draw_texture('yellow_box', 'star', x=(diff*offset), y=(j*tex.skin_config['yb_diff_offset'].y), color=color)
            if self.tja.metadata.course_data[diff].is_branching and (get_current_ms() // 1000) % 2 == 0:
                tex.draw_texture('yellow_box', 'branch_indicator', x=(diff*offset), color=color)

    def _draw_tja_data_diff(self, is_ura: bool, song_box: SongBox):
        if not self.tja:
            return
        tex.draw_texture('diff_select', 'back', fade=self.fade_in.attribute)
        tex.draw_texture('diff_select', 'option', fade=self.fade_in.attribute)
        tex.draw_texture('diff_select', 'neiro', fade=self.fade_in.attribute)

        offset_x = tex.skin_config['yb_diff_offset_diff_select'].x
        offset_y = tex.skin_config['yb_diff_offset_diff_select'].y
        for diff in self.tja.metadata.course_data:
            if diff >= Difficulty.URA:
                continue
            elif diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] == Crown.DFC:
                tex.draw_texture('yellow_box', 's_crown_dfc', x=(diff*offset_x)+tex.skin_config['yb_diff_offset_crown'].x, y=offset_y, fade=self.fade_in.attribute)
            elif diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] == Crown.FC:
                tex.draw_texture('yellow_box', 's_crown_fc', x=(diff*offset_x)+tex.skin_config['yb_diff_offset_crown'].x, y=offset_y, fade=self.fade_in.attribute)
            elif diff in song_box.scores and song_box.scores[diff] is not None and song_box.scores[diff][5] is not None and song_box.scores[diff][5] >= Crown.CLEAR:
                tex.draw_texture('yellow_box', 's_crown_clear', x=(diff*offset_x)+tex.skin_config['yb_diff_offset_crown'].x, y=offset_y, fade=self.fade_in.attribute)
            tex.draw_texture('yellow_box', 's_crown_outline', x=(diff*offset_x)+tex.skin_config['yb_diff_offset_crown'].x, y=offset_y, fade=min(self.fade_in.attribute, 0.25))

        for i in range(4):
            if i == Difficulty.ONI and is_ura:
                tex.draw_texture('diff_select', 'diff_tower', frame=4, x=(i*offset_x), fade=self.fade_in.attribute)
                tex.draw_texture('diff_select', 'ura_oni_plate', fade=self.fade_in.attribute)
            else:
                tex.draw_texture('diff_select', 'diff_tower', frame=i, x=(i*offset_x), fade=self.fade_in.attribute)
            if i not in self.tja.metadata.course_data:
                tex.draw_texture('diff_select', 'diff_tower_shadow', frame=i, x=(i*offset_x), fade=min(self.fade_in.attribute, 0.25))

        for course in self.tja.metadata.course_data:
            if (course == Difficulty.URA and not is_ura) or (course == Difficulty.ONI and is_ura):
                continue
            for j in range(self.tja.metadata.course_data[course].level):
                tex.draw_texture('yellow_box', 'star_ura', x=min(course, Difficulty.ONI)*offset_x, y=(j*tex.skin_config["yb_diff_offset_crown"].y), fade=self.fade_in.attribute)
            if self.tja.metadata.course_data[course].is_branching and (get_current_ms() // 1000) % 2 == 0:
                if course == Difficulty.URA:
                    name = 'branch_indicator_ura'
                else:
                    name = 'branch_indicator_diff'
                tex.draw_texture('yellow_box', name, x=min(course, Difficulty.ONI)*offset_x, fade=self.fade_in.attribute)

    def _draw_text(self, song_box, name: OutlinedText):
        if not isinstance(self.right_out, MoveAnimation):
            return
        if not isinstance(self.right_out_2, MoveAnimation):
            return
        if not isinstance(self.top_y_out, MoveAnimation):
            return
        x = song_box.position + (self.right_out.attribute*0.85 - (self.right_out.start_position*0.85)) + self.right_out_2.attribute - self.right_out_2.start_position
        if self.is_back:
            tex.draw_texture('box', 'back_text_highlight', x=x)
        else:
            texture = name.texture
            name.draw(outline_color=ray.BLACK, x=x + tex.skin_config["yb_name"].x, y=tex.skin_config["yb_name"].y + self.top_y_out.attribute, y2=min(texture.height, tex.skin_config["yb_name"].height)-texture.height, color=ray.WHITE)
        if self.subtitle is not None:
            texture = self.subtitle.texture
            y = self.bottom_y - min(texture.height, tex.skin_config["yb_subtitle"].height) + tex.skin_config["yb_subtitle"].y + self.top_y_out.attribute - self.top_y_out.start_position
            self.subtitle.draw(outline_color=ray.BLACK, x=x+tex.skin_config["yb_subtitle"].x, y=y, y2=min(texture.height, tex.skin_config["yb_subtitle"].height)-texture.height)

    def _draw_yellow_box(self):
        tex.draw_texture('yellow_box', 'yellow_box_bottom_right', x=self.right_x)
        tex.draw_texture('yellow_box', 'yellow_box_bottom_left', x=self.left_x, y=self.bottom_y)
        tex.draw_texture('yellow_box', 'yellow_box_top_right', x=self.right_x, y=self.top_y)
        tex.draw_texture('yellow_box', 'yellow_box_top_left', x=self.left_x, y=self.top_y)
        tex.draw_texture('yellow_box', 'yellow_box_bottom', x=self.left_x + self.edge_height, y=self.bottom_y, x2=self.center_width)
        tex.draw_texture('yellow_box', 'yellow_box_right', x=self.right_x, y=self.top_y + self.edge_height, y2=self.center_height)
        tex.draw_texture('yellow_box', 'yellow_box_left', x=self.left_x, y=self.top_y + self.edge_height, y2=self.center_height)
        tex.draw_texture('yellow_box', 'yellow_box_top', x=self.left_x + self.edge_height, y=self.top_y, x2=self.center_width)
        tex.draw_texture('yellow_box', 'yellow_box_center', x=self.left_x + self.edge_height, y=self.top_y + self.edge_height, x2=self.center_width, y2=self.center_height)

    def draw(self, song_box: Optional[SongBox | BackBox], fade_override: Optional[float], is_ura: bool, name: OutlinedText):
        self._draw_yellow_box()
        fade = self.fade.attribute
        if fade_override is not None:
            fade = min(self.fade.attribute, fade_override)
        if self.is_dan:
            return
        if self.is_back:
            tex.draw_texture('box', 'back_graphic', fade=fade)
            return
        if self.is_diff_select and isinstance(song_box, SongBox):
            self._draw_tja_data_diff(is_ura, song_box)
        elif isinstance(song_box, SongBox):
            self._draw_tja_data(song_box, ray.fade(ray.WHITE, fade), fade)

        self._draw_text(song_box, name)

class DanBox(BaseBox):
    def __init__(self, name, color: int, songs: list[tuple[TJAParser, int, int, int]], exams: list['Exam']):
        super().__init__(name, color)
        self.songs = songs
        self.exams = exams
        self.song_text: list[tuple[OutlinedText, OutlinedText]] = []
        self.total_notes = 0
        self.yellow_box = None
        for song, genre_index, difficulty, level in self.songs:
            notes, branch_m, branch_e, branch_n = song.notes_to_position(difficulty)
            self.total_notes += sum(1 for note in notes.play_notes if note.type < 5)
            for branch in branch_m:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)
            for branch in branch_e:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)
            for branch in branch_n:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)

    def load_text(self):
        super().load_text()
        self.hori_name = OutlinedText(self.text_name, tex.skin_config["dan_title"].font_size, ray.WHITE)
        for song, genre, difficulty, level in self.songs:
            title = song.metadata.title.get(global_data.config["general"]["language"], song.metadata.title["en"])
            subtitle = song.metadata.subtitle.get(global_data.config["general"]["language"], "")
            title_text = OutlinedText(title, tex.skin_config["dan_title"].font_size, ray.WHITE, vertical=True)
            font_size = tex.skin_config["dan_subtitle"].font_size if len(subtitle) < 30 else tex.skin_config["dan_subtitle"].font_size - int(10 * tex.screen_scale)
            subtitle_text = OutlinedText(subtitle, font_size, ray.WHITE, vertical=True)
            self.song_text.append((title_text, subtitle_text))
        self.text_loaded = True

    def update(self, current_time: float, is_diff_select: bool):
        super().update(current_time, is_diff_select)
        is_open_prev = self.is_open
        self.move_box(current_time)
        self.is_open = self.position == BOX_CENTER
        if not is_open_prev and self.is_open:
            self.yellow_box = YellowBox(False, is_dan=True)
            self.yellow_box.create_anim()

        if self.yellow_box is not None:
            self.yellow_box.update(True)

    def _draw_exam_box(self):
        tex.draw_texture('yellow_box', 'exam_box_bottom_right')
        tex.draw_texture('yellow_box', 'exam_box_bottom_left')
        tex.draw_texture('yellow_box', 'exam_box_top_right')
        tex.draw_texture('yellow_box', 'exam_box_top_left')
        tex.draw_texture('yellow_box', 'exam_box_bottom')
        tex.draw_texture('yellow_box', 'exam_box_right')
        tex.draw_texture('yellow_box', 'exam_box_left')
        tex.draw_texture('yellow_box', 'exam_box_top')
        tex.draw_texture('yellow_box', 'exam_box_center')
        tex.draw_texture('yellow_box', 'exam_header')

        offset = tex.skin_config["exam_box_offset"].y
        for i, exam in enumerate(self.exams):
            tex.draw_texture('yellow_box', 'judge_box', y=(i*offset))
            tex.draw_texture('yellow_box', 'exam_' + exam.type, y=(i*offset))
            counter = str(exam.red)
            margin = tex.skin_config["exam_counter_margin"].x
            if exam.type == 'gauge':
                tex.draw_texture('yellow_box', 'exam_percent', y=(i*offset))
                x_offset = tex.skin_config["exam_gauge_offset"].x
            else:
                x_offset = 0
            for j in range(len(counter)):
                tex.draw_texture('yellow_box', 'judge_num', frame=int(counter[j]), x=x_offset-(len(counter) - j) * margin, y=(i*offset))

            if exam.range == 'more':
                tex.draw_texture('yellow_box', 'exam_more', x=(x_offset*-1.7), y=(i*offset))
            elif exam.range == 'less':
                tex.draw_texture('yellow_box', 'exam_less', x=(x_offset*-1.7), y=(i*offset))

    def _draw_closed(self, x: float, y: float, outer_fade_override: float):
        tex.draw_texture('box', 'folder', frame=self.texture_index, x=x, fade=outer_fade_override)
        if self.name is not None:
            self.name.draw(outline_color=ray.BLACK, x=x + tex.skin_config["song_box_name"].x - int(self.name.texture.width / 2), y=y+(tex.skin_config["song_box_name"].height//2), y2=min(self.name.texture.height, tex.skin_config["song_box_name"].height)-self.name.texture.height, fade=outer_fade_override)

    def _draw_open(self, x: float, y: float, fade_override: Optional[float], is_ura: bool):
        if fade_override is not None:
            fade = fade_override
        else:
            fade = 1.0
        if self.yellow_box is not None:
            self.yellow_box.draw(None, None, False, self.name)
            for i, song in enumerate(self.song_text):
                title, subtitle = song
                x = i * tex.skin_config["dan_yellow_box_offset"].x
                tex.draw_texture('yellow_box', 'genre_banner', x=x, frame=self.songs[i][1], fade=fade)
                tex.draw_texture('yellow_box', 'difficulty', x=x, frame=self.songs[i][2], fade=fade)
                tex.draw_texture('yellow_box', 'difficulty_x', x=x, fade=fade)
                tex.draw_texture('yellow_box', 'difficulty_star', x=x, fade=fade)
                level = self.songs[i][0].metadata.course_data[self.songs[i][2]].level
                counter = str(level)
                margin = tex.skin_config["dan_level_counter_margin"].x
                total_width = len(counter) * margin
                for i in range(len(counter)):
                    tex.draw_texture('yellow_box', 'difficulty_num', frame=int(counter[i]), x=x-(total_width // 2) + (i * margin), fade=fade)

                title_data = tex.skin_config["dan_title"]
                subtitle_data = tex.skin_config["dan_subtitle"]
                title.draw(outline_color=ray.BLACK, x=title_data.x+x, y=title_data.y, y2=min(title.texture.height, title_data.height)-title.texture.height, fade=fade)
                subtitle.draw(outline_color=ray.BLACK, x=subtitle_data.x+x, y=subtitle_data.y-min(subtitle.texture.height, subtitle_data.height), y2=min(subtitle.texture.height, subtitle_data.height)-subtitle.texture.height, fade=fade)

            tex.draw_texture('yellow_box', 'total_notes_bg', fade=fade)
            tex.draw_texture('yellow_box', 'total_notes', fade=fade)
            counter = str(self.total_notes)
            for i in range(len(counter)):
                tex.draw_texture('yellow_box', 'total_notes_counter', frame=int(counter[i]), x=(i * tex.skin_config["total_notes_counter_margin"].x), fade=fade)

            tex.draw_texture('yellow_box', 'frame', frame=self.texture_index, fade=fade)
            if self.hori_name is not None:
                self.hori_name.draw(outline_color=ray.BLACK, x=tex.skin_config["dan_hori_name"].x - (self.hori_name.texture.width//2), y=tex.skin_config["dan_hori_name"].y, x2=min(self.hori_name.texture.width, tex.skin_config["dan_hori_name"].width)-self.hori_name.texture.width, fade=fade)

            self._draw_exam_box()

class GenreBG:
    """The background for a genre box."""
    def __init__(self, start_box: BaseBox, end_box: BaseBox, title: OutlinedText, diff_sort: Optional[int]):
        self.start_box = start_box
        self.end_box = end_box
        self.start_position = start_box.position
        self.end_position_final = end_box.position
        self.title = title
        self.fade_in = Animation.create_fade(133, initial_opacity=0.0, final_opacity=1.0, ease_in='quadratic', delay=50)
        self.fade_in.start()
        self.move = Animation.create_move(316, delay=self.fade_in.duration/2, total_distance=abs(self.end_position_final - self.start_position), ease_in='quadratic')
        self.move.start()
        self.box_fade_in = Animation.create_fade(66.67*2, delay=self.move.duration, initial_opacity=0.0, final_opacity=1.0)
        self.box_fade_in.start()
        self.end_position = self.start_position + self.move.attribute
        self.diff_num = diff_sort
    def update(self, current_ms):
        self.start_position = self.start_box.position
        #self.end_position_final = self.end_box.position
        self.end_position = self.start_position + self.move.attribute
        if self.move.is_finished:
            self.end_position = self.end_box.position
        self.box_fade_in.update(current_ms)
        self.fade_in.update(current_ms)
        self.move.update(current_ms)
    def draw(self, y):
        offset = (tex.skin_config["genre_bg_offset"].x * -1) if self.start_box.is_open else 0

        tex.draw_texture('box', 'folder_background_edge', frame=self.end_box.texture_index, x=self.start_position+offset, y=y, mirror="horizontal", fade=self.fade_in.attribute)


        extra_distance = tex.skin_config["genre_bg_extra_distance"].x if self.end_box.is_open or (self.start_box.is_open and (844 * tex.screen_scale) <= self.end_position <= (1144 * tex.screen_scale)) else 0
        if self.start_position >= tex.skin_config["genre_bg_left_max"].x and self.end_position < self.start_position:
            x2 = self.start_position + tex.skin_config["genre_bg_offset_2"].x
            x = self.start_position+offset
        elif (self.start_position <= tex.skin_config["genre_bg_left_max"].x) and (self.end_position < self.start_position):
            x = 0
            x2 = tex.screen_width
        else:
            x2 = abs(self.end_position) - self.start_position + extra_distance + (-1 * tex.skin_config["genre_bg_left_max"].x + (1 * tex.screen_scale))
            x = self.start_position+offset
        tex.draw_texture('box', 'folder_background', x=x, y=y, x2=x2, frame=self.end_box.texture_index)


        if self.end_position < self.start_position and self.end_position >= tex.skin_config["genre_bg_left_max"].x:
            x2 = min(self.end_position+tex.skin_config["genre_bg_folder_background"].width, tex.screen_width) + extra_distance
            tex.draw_texture('box', 'folder_background', x=tex.skin_config["genre_bg_folder_background"].x, y=y, x2=x2, frame=self.end_box.texture_index)


        offset = tex.skin_config["genre_bg_offset"].x if self.end_box.is_open else 0
        tex.draw_texture('box', 'folder_background_edge', x=self.end_position+tex.skin_config["genre_bg_folder_edge"].x+offset, y=y, fade=self.fade_in.attribute, frame=self.end_box.texture_index)

        if ((self.start_position <= BOX_CENTER and self.end_position >= BOX_CENTER) or
            ((self.start_position <= BOX_CENTER or self.end_position >= BOX_CENTER) and (self.start_position > self.end_position))):
            offset = tex.skin_config["genre_bg_offset_3"].x if self.diff_num is not None else 0
            dest_width = min(tex.skin_config["genre_bg_title"].width, self.title.texture.width)
            tex.draw_texture('box', 'folder_background_folder', x=-((offset+dest_width)//2), y=y+tex.skin_config["genre_bg_folder_background_folder"].y, x2=dest_width+offset++tex.skin_config["genre_bg_folder_background_folder"].width, fade=self.fade_in.attribute, frame=self.end_box.texture_index)
            tex.draw_texture('box', 'folder_background_folder_edge', x=-((offset+dest_width)//2), y=y+tex.skin_config["genre_bg_folder_background_folder"].y, fade=self.fade_in.attribute, frame=self.end_box.texture_index, mirror="horizontal")
            tex.draw_texture('box', 'folder_background_folder_edge', x=((offset+dest_width)//2)+tex.skin_config["genre_bg_folder_background_folder"].x, y=y+tex.skin_config["genre_bg_folder_background_folder"].y, fade=self.fade_in.attribute, frame=self.end_box.texture_index)
            if self.diff_num is not None:
                tex.draw_texture('diff_sort', 'star_num', frame=self.diff_num, x=(tex.skin_config["genre_bg_offset"].x * -1) + (dest_width//2), y=tex.skin_config["diff_sort_star_num"].y)
            self.title.draw(outline_color=ray.BLACK, x=(tex.screen_width//2) - (dest_width//2)-(offset//2), y=y+tex.skin_config["genre_bg_title"].y, x2=dest_width - self.title.texture.width, color=ray.fade(ray.WHITE, self.fade_in.attribute))

class ScoreHistory:
    """The score information that appears while hovering over a song"""
    def __init__(self, scores: dict[int, tuple[int, int, int, int]], current_ms):
        """
        Initialize the score history with the given scores and current time.

        Args:
            scores (dict[int, tuple[int, int, int, int]]): A dictionary of scores for each difficulty level.
            current_ms (int): The current time in milliseconds.
        """
        self.scores = {k: v for k, v in scores.items() if v is not None}
        self.difficulty_keys = list(self.scores.keys())
        self.curr_difficulty_index = 0
        self.curr_difficulty_index = (self.curr_difficulty_index + 1) % len(self.difficulty_keys)
        self.curr_difficulty = self.difficulty_keys[self.curr_difficulty_index]
        self.curr_score = self.scores[self.curr_difficulty][0]
        self.curr_score_su = self.scores[self.curr_difficulty][0]
        self.last_ms = current_ms
        self.long = True

    def update(self, current_ms):
        if current_ms >= self.last_ms + 1000:
            self.last_ms = current_ms
            self.curr_difficulty_index = (self.curr_difficulty_index + 1) % len(self.difficulty_keys)
            self.curr_difficulty = self.difficulty_keys[self.curr_difficulty_index]
            self.curr_score = self.scores[self.curr_difficulty][0]
            self.curr_score_su = self.scores[self.curr_difficulty][0]

    def draw_long(self):
        tex.draw_texture('leaderboard','background_2')
        tex.draw_texture('leaderboard','title', index=self.long)
        if self.curr_difficulty == Difficulty.URA:
            tex.draw_texture('leaderboard', 'shinuchi_ura', index=self.long)
        else:
            tex.draw_texture('leaderboard', 'shinuchi', index=self.long)

        tex.draw_texture('leaderboard', 'pts', color=ray.WHITE, index=self.long)
        tex.draw_texture('leaderboard', 'difficulty', frame=self.curr_difficulty, index=self.long)

        for i in range(4):
            tex.draw_texture('leaderboard', 'normal', index=self.long, y=tex.skin_config["score_info_bg_offset"].y+(i*tex.skin_config["score_info_bg_offset"].y))

        tex.draw_texture('leaderboard', 'judge_good')
        tex.draw_texture('leaderboard', 'judge_ok')
        tex.draw_texture('leaderboard', 'judge_bad')
        tex.draw_texture('leaderboard', 'judge_drumroll')

        for j, counter in enumerate(self.scores[self.curr_difficulty]):
            if j == Difficulty.TOWER:
                continue
            if counter is None:
                continue
            counter = str(counter)
            margin = tex.skin_config["score_info_counter_margin"].x
            for i in range(len(counter)):
                if j == 0:
                    tex.draw_texture('leaderboard', 'counter', frame=int(counter[i]), x=-((len(counter) * tex.skin_config["score_info_counter_margin"].width) // 2) + (i * tex.skin_config["score_info_counter_margin"].width), color=ray.WHITE, index=self.long)
                else:
                    tex.draw_texture('leaderboard', 'judge_num', frame=int(counter[i]), x=-(len(counter) - i) * margin, y=j*tex.skin_config["score_info_bg_offset"].y)

    def draw(self):
        if self.long:
            self.draw_long()
            return
        tex.draw_texture('leaderboard','background')
        tex.draw_texture('leaderboard','title')

        if self.curr_difficulty == Difficulty.URA:
            tex.draw_texture('leaderboard', 'normal_ura')
            tex.draw_texture('leaderboard', 'shinuchi_ura')
        else:
            tex.draw_texture('leaderboard', 'normal')
            tex.draw_texture('leaderboard', 'shinuchi')

        color = ray.BLACK
        if self.curr_difficulty == Difficulty.URA:
            color = ray.WHITE
            tex.draw_texture('leaderboard','ura')

        tex.draw_texture('leaderboard', 'pts', color=color)
        tex.draw_texture('leaderboard', 'pts', y=tex.skin_config["score_info_bg_offset"].y)

        tex.draw_texture('leaderboard', 'difficulty', frame=self.curr_difficulty)

        counter = str(self.curr_score)
        total_width = len(counter) * tex.skin_config["score_info_counter_margin"].width
        for i in range(len(counter)):
            tex.draw_texture('leaderboard', 'counter', frame=int(counter[i]), x=-(total_width // 2) + (i * tex.skin_config["score_info_counter_margin"].width), color=color)

        counter = str(self.curr_score_su)
        total_width = len(counter) * tex.skin_config["score_info_counter_margin"].width
        for i in range(len(counter)):
            tex.draw_texture('leaderboard', 'counter', frame=int(counter[i]), x=-(total_width // 2) + (i * tex.skin_config["score_info_counter_margin"].width), y=tex.skin_config["score_info_bg_offset"].y, color=ray.WHITE)

def parse_box_def(path: Path):
    """Parse box.def file for directory metadata"""
    texture_index = SongBox.DEFAULT_INDEX
    name = path.name
    genre = ''
    collection = None
    encoding = test_encodings(path / "box.def")

    try:
        with open(path / "box.def", 'r', encoding=encoding) as box_def:
            for line in box_def:
                line = line.strip()
                if line.startswith("#GENRE:"):
                    genre = line.split(":", 1)[1].strip()
                    texture_index = FileSystemItem.GENRE_MAP.get(genre, SongBox.DEFAULT_INDEX)
                    if texture_index == SongBox.DEFAULT_INDEX:
                        texture_index = FileSystemItem.GENRE_MAP_2.get(genre, SongBox.DEFAULT_INDEX)
                elif line.startswith("#TITLE:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("#TITLEJA:"):
                    if global_data.config['general']['language'] == 'ja':
                        name = line.split(":", 1)[1].strip()
                elif line.startswith("#COLLECTION"):
                    collection = line.split(":", 1)[1].strip()
                if name == '':
                    if genre:
                        name = genre
                    else:
                        name = path.name
    except Exception as e:
        logger.error(f"Error parsing box.def in {path}: {e}")

    return name, texture_index, collection

class FileSystemItem:
    GENRE_MAP = {
        'J-POP': 1,
        'アニメ': 2,
        'VOCALOID': 3,
        'どうよう': 4,
        'バラエティー': 5,
        'クラシック': 6,
        'ゲームミュージック': 7,
        'ナムコオリジナル': 8,
        'RECOMMENDED': 10,
        'FAVORITE': 11,
        'RECENT': 12,
        '段位道場': 13,
        'DIFFICULTY': 14
    }
    GENRE_MAP_2 = {
        'ボーカロイド': 3,
        'バラエティ': 5
    }
    """Base class for files and directories in the navigation system"""
    def __init__(self, path: Path, name: str):
        self.path = path
        self.name = name

class Directory(FileSystemItem):
    """Represents a directory in the navigation system"""
    COLLECTIONS = [
        'NEW',
        'RECENT',
        'FAVORITE',
        'DIFFICULTY',
        'RECOMMENDED'
    ]
    def __init__(self, path: Path, name: str, texture_index: int, has_box_def=False, to_root=False, back=False, tja_count=0, box_texture=None, collection=None):
        super().__init__(path, name)
        self.has_box_def = has_box_def
        self.to_root = to_root
        self.back = back
        self.tja_count = tja_count
        self.collection = None
        if collection in Directory.COLLECTIONS:
            self.collection = collection
        if collection in FileSystemItem.GENRE_MAP:
            texture_index = FileSystemItem.GENRE_MAP[collection]
        elif self.to_root or self.back:
            texture_index = SongBox.BACK_INDEX

        if self.back:
            self.box = BackBox(name, texture_index)
        else:
            self.box = FolderBox(name, texture_index, tja_count=tja_count, box_texture=box_texture)

class SongFile(FileSystemItem):
    """Represents a song file (TJA) in the navigation system"""
    def __init__(self, path: Path, name: str, texture_index: int, tja=None, name_texture_index: Optional[int]=None):
        super().__init__(path, name)
        self.is_recent = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)) <= timedelta(days=7)
        self.tja = tja or TJAParser(path)
        if self.is_recent:
            self.tja.ex_data.new = True
        title = self.tja.metadata.title.get(global_data.config['general']['language'].lower(), self.tja.metadata.title['en'])
        self.hash = global_data.song_paths[path]
        self.box = SongBox(title, texture_index, self.tja, name_texture_index=name_texture_index if name_texture_index is not None else texture_index)
        self.box.hash = global_data.song_hashes[self.hash][0]["diff_hashes"]
        self.box.get_scores()

@dataclass
class Exam:
    type: str
    red: int
    gold: int
    range: str

class DanCourse(FileSystemItem):
    def __init__(self, path: Path, name: str):
        super().__init__(path, name)
        if name != "dan.json":
            logger.error(f"Invalid dan course file: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.title = data["title"]
            self.color = data["color"]
            self.charts: list[tuple[TJAParser, int, int, int]] = []
            for chart in data["charts"]:
                hash = chart["hash"]
                #chart_title = chart["title"]
                #chart_subtitle = chart["subtitle"]
                difficulty = chart["difficulty"]
                if hash in global_data.song_hashes:
                    path = Path(global_data.song_hashes[hash][0]["file_path"])
                    if (path.parent.parent / "box.def").exists():
                        _, genre_index, _ = parse_box_def(path.parent.parent)
                    else:
                        genre_index = 9
                    tja = TJAParser(path)
                    self.charts.append((tja, genre_index, difficulty, tja.metadata.course_data[difficulty].level))
                else:
                    pass
                    #do something with song_title, song_subtitle
            self.exams = []
            for exam in data["exams"]:
                self.exams.append(Exam(exam["type"], exam["value"][0], exam["value"][1], exam["range"]))

        self.box = DanBox(self.title, self.color, self.charts, self.exams)

class FileNavigator:
    """Manages navigation through pre-generated Directory and SongFile objects"""
    def __init__(self):

        # Pre-generated objects storage
        self.all_directories: dict[str, Directory] = {}  # path -> Directory
        self.all_song_files: dict[str, Union[SongFile, DanCourse]] = {}    # path -> SongFile
        self.directory_contents: dict[str, list[Union[Directory, SongFile]]] = {}  # path -> list of items

        # OPTION 2: Lazy crown calculation with caching
        self.directory_crowns: dict[str, dict] = dict()  # path -> crown list
        self.crown_cache_dirty: set[str] = set()  # directories that need crown recalculation

        # Navigation state - simplified without root-specific state
        self.current_dir = Path()  # Empty path represents virtual root
        self.items: list[Directory | SongFile] = []
        self.new_items: list[Directory | SongFile] = []
        self.favorite_folder: Optional[Directory] = None
        self.recent_folder: Optional[Directory] = None
        self.selected_index = 0
        self.diff_sort_diff = Difficulty.URA
        self.diff_sort_level = 10
        self.diff_sort_statistics = dict()
        self.history = []
        self.box_open = False
        self.genre_bg = None
        self.song_count = 0
        self.in_dan_select = False
        logger.info("FileNavigator initialized")

    def initialize(self, root_dirs: list[Path]):
        self.root_dirs = [Path(p) if not isinstance(p, Path) else p for p in root_dirs]
        self._generate_all_objects()
        self._create_virtual_root()
        self.load_current_directory()
        logger.info(f"FileNavigator initialized with root_dirs: {self.root_dirs}")

    def _create_virtual_root(self):
        """Create a virtual root directory containing all root directories"""
        virtual_root_items = []

        for root_path in self.root_dirs:
            if not root_path.exists():
                continue

            root_key = str(root_path)
            if root_key in self.all_directories:
                # Root has box.def, add the directory itself
                virtual_root_items.append(self.all_directories[root_key])
            else:
                # Root doesn't have box.def, add its immediate children with box.def
                for child_path in sorted(root_path.iterdir()):
                    if child_path.is_dir():
                        child_key = str(child_path)
                        if child_key in self.all_directories:
                            virtual_root_items.append(self.all_directories[child_key])

                # Also add direct TJA files from root
                all_tja_files = self._find_tja_files_recursive(root_path)
                for tja_path in sorted(all_tja_files):
                    song_key = str(tja_path)
                    if song_key in self.all_song_files:
                        virtual_root_items.append(self.all_song_files[song_key])

        # Store virtual root contents (empty path key represents root)
        self.directory_contents["."] = virtual_root_items

    def _generate_all_objects(self):
        """Generate all Directory and SongFile objects in advance"""
        logging.info("Generating all Directory and SongFile objects...")

        # Generate objects for each root directory
        for root_path in self.root_dirs:
            if not root_path.exists():
                logging.warning(f"Root directory does not exist: {root_path}")
                continue

            self._generate_objects_recursive(root_path)

        if self.favorite_folder is not None:
            song_list = self._read_song_list(self.favorite_folder.path)
            for song_obj in song_list:
                if str(song_obj) in self.all_song_files:
                    box = self.all_song_files[str(song_obj)].box
                    if isinstance(box, DanBox):
                        logger.warning(f"Cannot favorite DanCourse: {song_obj}")
                    else:
                        box.is_favorite = True

        logging.info(f"Object generation complete. "
                    f"Directories: {len(self.all_directories)}, "
                    f"Songs: {len(self.all_song_files)}")

    def _generate_objects_recursive(self, dir_path: Path):
        """Recursively generate Directory and SongFile objects for a directory"""
        if not dir_path.is_dir():
            return

        dir_key = str(dir_path)

        # Check for box.def
        has_box_def = (dir_path / "box.def").exists()

        # Only create Directory objects for directories with box.def
        if has_box_def:
            # Parse box.def if it exists
            name = dir_path.name if dir_path.name else str(dir_path)
            texture_index = SongBox.DEFAULT_INDEX
            box_texture = None
            collection = None

            name, texture_index, collection = parse_box_def(dir_path)
            box_png_path = dir_path / "box.png"
            if box_png_path.exists():
                box_texture = str(box_png_path)

            # Count TJA files for this directory
            tja_count = self._count_tja_files(dir_path)
            if collection == Directory.COLLECTIONS[4]:
                tja_count = 10
            elif collection == Directory.COLLECTIONS[0]:
                tja_count = len(self.new_items)

            # Create Directory object
            directory_obj = Directory(
                dir_path, name, texture_index,
                has_box_def=has_box_def,
                tja_count=tja_count,
                box_texture=box_texture,
                collection=collection
            )
            if directory_obj.collection == Directory.COLLECTIONS[2]:
                self.favorite_folder = directory_obj
            elif directory_obj.collection == Directory.COLLECTIONS[1]:
                self.recent_folder = directory_obj
            self.all_directories[dir_key] = directory_obj

            # Generate content list for this directory
            content_items = []

            # Add child directories that have box.def
            child_dirs = []
            for item_path in dir_path.iterdir():
                if item_path.is_dir():
                    child_has_box_def = (item_path / "box.def").exists()
                    if child_has_box_def:
                        child_dirs.append(item_path)
                        # Recursively generate objects for child directory
                        self._generate_objects_recursive(item_path)

            # Sort and add child directories
            for child_path in sorted(child_dirs):
                child_key = str(child_path)
                if child_key in self.all_directories:
                    content_items.append(self.all_directories[child_key])

            # Get TJA files for this directory
            tja_files = self._get_tja_files_for_directory(dir_path)

            # Create SongFile objects
            for tja_path in sorted(tja_files):
                song_key = str(tja_path)
                if song_key not in self.all_song_files and tja_path.name == "dan.json":
                    valid_dan = True
                    with open(tja_path, 'r', encoding='utf-8') as file:
                        dan_data = json.load(file)
                        for chart in dan_data["charts"]:
                            hash = chart["hash"]
                            if hash not in global_data.song_hashes:
                                valid_dan = False
                    if valid_dan:
                        song_obj = DanCourse(tja_path, tja_path.name)
                        self.all_song_files[song_key] = song_obj
                elif song_key not in self.all_song_files and tja_path in global_data.song_paths:
                    song_obj = SongFile(tja_path, tja_path.name, texture_index)
                    song_obj.box.get_scores()
                    for course in song_obj.tja.metadata.course_data:
                        level = song_obj.tja.metadata.course_data[course].level

                        scores = song_obj.box.scores.get(course)
                        if scores is not None:
                            is_cleared = scores[4] >= Crown.CLEAR if scores[4] is not None else False
                            is_full_combo = scores[4] == Crown.FC if scores[4] is not None else False
                        else:
                            is_cleared = False
                            is_full_combo = False

                        if course not in self.diff_sort_statistics:
                            self.diff_sort_statistics[course] = {}

                        if level not in self.diff_sort_statistics[course]:
                            self.diff_sort_statistics[course][level] = [1, int(is_full_combo), int(is_cleared)]
                        else:
                            self.diff_sort_statistics[course][level][0] += 1
                            if is_full_combo:
                                self.diff_sort_statistics[course][level][1] += 1
                            elif is_cleared:
                                self.diff_sort_statistics[course][level][2] += 1
                    if song_obj.is_recent:
                        self.new_items.append(SongFile(tja_path, tja_path.name, SongBox.DEFAULT_INDEX, name_texture_index=texture_index))
                    self.song_count += 1
                    global_data.song_progress = self.song_count / global_data.total_songs
                    self.all_song_files[song_key] = song_obj

                if song_key in self.all_song_files:
                    content_items.append(self.all_song_files[song_key])

            self.directory_contents[dir_key] = content_items

        else:
            # For directories without box.def, still process their children
            for item_path in dir_path.iterdir():
                if item_path.is_dir():
                    self._generate_objects_recursive(item_path)

            # Create SongFile objects for TJA files in non-boxed directories
            tja_files = self._find_tja_files_in_directory_only(dir_path)
            for tja_path in tja_files:
                song_key = str(tja_path)
                if song_key not in self.all_song_files:
                    try:
                        song_obj = SongFile(tja_path, tja_path.name, SongBox.DEFAULT_INDEX)
                        self.song_count += 1
                        global_data.song_progress = self.song_count / global_data.total_songs
                        self.all_song_files[song_key] = song_obj
                    except Exception as e:
                        logger.error(f"Error creating SongFile for {tja_path}: {e}")
                        continue

    def is_at_root(self) -> bool:
        """Check if currently at the virtual root"""
        return self.current_dir == Path()

    def load_current_directory(self, selected_item: Optional[Directory] = None):
        """Load pre-generated items for the current directory (unified for root and subdirs)"""
        dir_key = str(self.current_dir)

        # Determine if current directory has child directories with box.def
        has_children = False
        if self.is_at_root() or selected_item and selected_item.box.texture_index == 13:
            has_children = True  # Root always has "children" (the root directories)
        else:
            has_children = any(item.is_dir() and (item / "box.def").exists()
                             for item in self.current_dir.iterdir())

        self.genre_bg = None
        self.in_favorites = False

        if has_children:
            self.items = []
            if not self.box_open:
                self.selected_index = 0

        start_box = None
        end_box = None

        # Add back navigation item (only if not at root)
        if not self.is_at_root():
            back_dir = Directory(self.current_dir.parent, "", SongBox.BACK_INDEX, back=True)
            if not has_children:
                start_box = back_dir.box
            self.items.insert(self.selected_index, back_dir)

        # Add pre-generated content for this directory
        if dir_key in self.directory_contents:
            content_items = self.directory_contents[dir_key]

            # Handle special collections (same logic as before)
            if isinstance(selected_item, Directory):
                if selected_item.collection == Directory.COLLECTIONS[0]:
                    content_items = self.new_items
                elif selected_item.collection == Directory.COLLECTIONS[1]:
                    if self.recent_folder is None:
                        raise Exception("tried to enter recent folder without recents")
                    self._generate_objects_recursive(self.recent_folder.path)
                    if not isinstance(selected_item.box, BackBox):
                        selected_item.box.tja_count = self._count_tja_files(self.recent_folder.path)
                    content_items = self.directory_contents[dir_key]
                elif selected_item.collection == Directory.COLLECTIONS[2]:
                    if self.favorite_folder is None:
                        raise Exception("tried to enter favorite folder without favorites")
                    self._generate_objects_recursive(self.favorite_folder.path)
                    tja_files = self._get_tja_files_for_directory(self.favorite_folder.path)
                    self._calculate_directory_crowns(dir_key, tja_files)
                    if not isinstance(selected_item.box, BackBox):
                        selected_item.box.tja_count = self._count_tja_files(self.favorite_folder.path)
                    content_items = self.directory_contents[dir_key]
                    self.in_favorites = True
                elif selected_item.collection == Directory.COLLECTIONS[3]:
                    content_items = []
                    parent_dir = selected_item.path.parent
                    for sibling_path in parent_dir.iterdir():
                        if sibling_path.is_dir() and sibling_path != selected_item.path:
                            sibling_key = str(sibling_path)
                            if sibling_key in self.directory_contents:
                                for item in self.directory_contents[sibling_key]:
                                    if isinstance(item, SongFile) and item:
                                        if self.diff_sort_diff in item.tja.metadata.course_data and item.tja.metadata.course_data[self.diff_sort_diff].level == self.diff_sort_level:
                                            if item not in content_items:
                                                content_items.append(item)
                elif selected_item.collection == Directory.COLLECTIONS[4]:
                    parent_dir = selected_item.path.parent
                    temp_items = []
                    for sibling_path in parent_dir.iterdir():
                        if sibling_path.is_dir() and sibling_path != selected_item.path:
                            sibling_key = str(sibling_path)
                            if sibling_key in self.directory_contents:
                                for item in self.directory_contents[sibling_key]:
                                    if not isinstance(item, Directory) and isinstance(item, SongFile):
                                        temp_items.append(item)
                    content_items = random.sample(temp_items, min(10, len(temp_items)))

            if content_items == []:
                self.go_back()
                return
            i = 1
            for item in content_items:
                if isinstance(item, SongFile) and not has_children:
                    if i % 10 == 0 and i != 0:
                        back_dir = Directory(self.current_dir.parent, "", SongBox.BACK_INDEX, back=True)
                        self.items.insert(self.selected_index+i, back_dir)
                        i += 1
                if not has_children:
                    if selected_item is not None:
                        item.box.texture_index = selected_item.box.texture_index
                    self.items.insert(self.selected_index+i, item)
                else:
                    self.items.append(item)
                i += 1

            if not has_children:
                self.box_open = True
                end_box = content_items[-1].box
                if selected_item in self.items:
                    self.items.remove(selected_item)

        # Calculate crowns for directories
        for item in self.items:
            if isinstance(item, Directory):
                item_key = str(item.path)
                if isinstance(item.box, FolderBox):
                    item.box.crown = self._get_directory_crowns_cached(item_key)

        self.calculate_box_positions()

        if selected_item and isinstance(selected_item.box, FolderBox):
            if (not has_children and start_box is not None
                and end_box is not None and selected_item is not None
                and selected_item.box.hori_name is not None):
                hori_name = selected_item.box.hori_name
                diff_sort = None
                if selected_item.collection == Directory.COLLECTIONS[3]:
                    diff_sort = self.diff_sort_level
                    diffs = ['かんたん', 'ふつう', 'むずかしい', 'おに']
                    hori_name = OutlinedText(diffs[min(Difficulty.ONI, self.diff_sort_diff)], tex.skin_config["song_hori_name"].font_size, ray.WHITE, outline_thickness=5)
                self.genre_bg = GenreBG(start_box, end_box, hori_name, diff_sort)

    def select_current_item(self):
        """Select the currently highlighted item"""
        if not self.items or self.selected_index >= len(self.items):
            return

        selected_item = self.items[self.selected_index]

        if isinstance(selected_item, Directory):
            if self.box_open:
                self.go_back()

            if selected_item.back:
                # Handle back navigation
                if self.current_dir.parent == Path():
                    # Going back to root
                    self.current_dir = Path()
                else:
                    self.current_dir = self.current_dir.parent
            else:
                # Save current state to history
                self.history.append((self.current_dir, self.selected_index))
                self.current_dir = selected_item.path
                logger.info(f"Entered Directory {selected_item.path}")

            self.load_current_directory(selected_item=selected_item)

        return selected_item

    def go_back(self):
        """Navigate back to the previous directory"""
        if self.history:
            previous_dir, previous_index = self.history.pop()
            self.current_dir = previous_dir
            self.selected_index = previous_index
            self.load_current_directory()
            self.box_open = False

    def _count_tja_files(self, folder_path: Path):
        """Count TJA files in directory"""
        tja_count = 0

        # Find all song_list.txt files recursively
        song_list_files = list(folder_path.rglob("song_list.txt"))

        if song_list_files:
            # Process all song_list.txt files found
            for song_list_path in song_list_files:
                with open(song_list_path, 'r', encoding='utf-8-sig') as song_list_file:
                    tja_count += len([line for line in song_list_file.readlines() if line.strip()])
        # Fallback: Use recursive counting of .tja or dan.json files
        tja_count += sum(1 for _ in list(folder_path.rglob("*.tja")) + list(folder_path.rglob("dan.json")))

        return tja_count

    def _get_directory_crowns_cached(self, dir_key: str) -> dict:
        """Get crowns for a directory, calculating only if needed"""
        if dir_key in self.crown_cache_dirty or dir_key not in self.directory_crowns:
            # Calculate crowns on-demand
            tja_files = self.directory_contents[dir_key]
            self._calculate_directory_crowns(dir_key, tja_files)
            self.crown_cache_dirty.discard(dir_key)

        return self.directory_crowns.get(dir_key, dict())

    def _calculate_directory_crowns(self, dir_key: str, tja_files: list):
        """Pre-calculate crowns for a directory"""
        all_scores = dict()
        child_has_any_crown = []  # Track if each child has been played at all

        for item in tja_files:
            has_crown = False
            if isinstance(item, SongFile):
                has_crown = any((item.box.scores.get(d) or (None,)*6)[5] is not None
                              for d in [Difficulty.EASY, Difficulty.NORMAL, Difficulty.HARD, Difficulty.ONI])
                for diff in item.box.scores:
                    if diff not in all_scores:
                        all_scores[diff] = []
                    all_scores[diff].append(item.box.scores[diff])
            elif isinstance(item, Directory):
                child_key = str(item.path)
                child_crowns = self._get_directory_crowns_cached(child_key)
                has_crown = bool(child_crowns)  # Directory is "played" if it has any crowns

                if not child_crowns:
                    # Unplayed directory - add None for all difficulties
                    for diff in [Difficulty.EASY, Difficulty.NORMAL, Difficulty.HARD, Difficulty.ONI]:
                        if diff not in all_scores:
                            all_scores[diff] = []
                        all_scores[diff].append((None, None, None, None, None, None))
                else:
                    # Played directory - add its crowns
                    for diff in [Difficulty.EASY, Difficulty.NORMAL, Difficulty.HARD, Difficulty.ONI]:
                        if diff not in all_scores:
                            all_scores[diff] = []
                        if diff in child_crowns:
                            all_scores[diff].append((None, None, None, None, None, child_crowns[diff]))
                        else:
                            # This directory doesn't have this difficulty, but it's been played
                            # Don't add anything - this child doesn't count for this difficulty
                            pass

            child_has_any_crown.append(has_crown)

        # If ANY child is completely unplayed, no crowns at all
        if not all(child_has_any_crown):
            self.directory_crowns[dir_key] = {}
            return

        crowns = {}
        for diff in all_scores:
            if any(score is None or score[5] is None for score in all_scores[diff]):
                continue
            if all(score[5] == Crown.DFC for score in all_scores[diff]):
                crowns[diff] = Crown.DFC
            elif all(score[5] == Crown.FC for score in all_scores[diff]):
                crowns[diff] = Crown.FC
            elif all(score[5] >= Crown.CLEAR for score in all_scores[diff]):
                crowns[diff] = Crown.CLEAR

        self.directory_crowns[dir_key] = crowns

    def _get_tja_files_for_directory(self, directory: Path):
        """Get TJA files for a specific directory"""
        if (directory / 'song_list.txt').exists():
            return self._read_song_list(directory)
        else:
            return self._find_tja_files_in_directory_only(directory)

    def _find_tja_files_in_directory_only(self, directory: Path):
        """Find TJA files only in the specified directory, not recursively in subdirectories with box.def"""
        tja_files: list[Path] = []

        for path in directory.iterdir():
            if (path.is_file() and path.suffix.lower() == ".tja") or path.name == "dan.json":
                tja_files.append(path)
            elif path.is_dir():
                # Only recurse into subdirectories that don't have box.def
                sub_dir_has_box_def = (path / "box.def").exists()
                if not sub_dir_has_box_def:
                    tja_files.extend(self._find_tja_files_in_directory_only(path))

        return tja_files

    def _find_tja_files_recursive(self, directory: Path, box_def_dirs_only=True):
        tja_files: list[Path] = []

        has_box_def = (directory / "box.def").exists()
        if box_def_dirs_only and has_box_def and directory != self.current_dir:
            return []

        for path in directory.iterdir():
            if path.is_file() and path.suffix.lower() == ".tja":
                tja_files.append(path)
            elif path.is_dir():
                sub_dir_has_box_def = (path / "box.def").exists()
                if not sub_dir_has_box_def:
                    tja_files.extend(self._find_tja_files_recursive(path, box_def_dirs_only))

        return tja_files

    def _read_song_list(self, path: Path):
        """Read and process song_list.txt file"""
        tja_files: list[Path] = []
        updated_lines = []
        file_updated = False
        with open(path / 'song_list.txt', 'r', encoding='utf-8-sig') as song_list:
            for line in song_list:
                line = line.strip()
                if not line:
                    continue

                parts = line.split('|')
                if len(parts) < 3:
                    continue

                hash_val, title, subtitle = parts[0], parts[1], parts[2]
                original_hash = hash_val

                if hash_val in global_data.song_hashes:
                    for entry in global_data.song_hashes[hash_val]:
                        file_path = Path(entry["file_path"])
                        if file_path.exists() and file_path not in tja_files:
                            tja_files.append(file_path)
                else:
                    # Try to find by title and subtitle
                    for key, value in global_data.song_hashes.items():
                        for i in range(len(value)):
                            song = value[i]
                            if (song["title"]["en"].strip() == title and
                                song["subtitle"]["en"].strip() == subtitle.removeprefix('--') and
                                Path(song["file_path"]).exists()):
                                hash_val = key
                                tja_files.append(Path(global_data.song_hashes[hash_val][i]["file_path"]))
                                break

                if hash_val != original_hash:
                    file_updated = True
                updated_lines.append(f"{hash_val}|{title}|{subtitle.removeprefix('--')}")

        # Write back updated song list if needed
        if file_updated:
            with open(path / 'song_list.txt', 'w', encoding='utf-8-sig') as song_list:
                for line in updated_lines:
                    logger.info(f"updated: {line}")
                    song_list.write(line + '\n')

        return tja_files

    def calculate_box_positions(self):
        """Dynamically calculate box positions based on current selection with wrap-around support"""
        if not self.items:
            return

        for i, item in enumerate(self.items):
            offset = i - self.selected_index

            if offset > len(self.items) // 2:
                offset -= len(self.items)
            elif offset < -len(self.items) // 2:
                offset += len(self.items)

            # Adjust spacing based on dan select mode
            base_spacing = 100 * tex.screen_scale
            center_offset = 150 * tex.screen_scale
            side_offset_l = 0 * tex.screen_scale
            side_offset_r = 300 * tex.screen_scale

            if self.in_dan_select:
                base_spacing = 150 * tex.screen_scale
                side_offset_l = 200 * tex.screen_scale
                side_offset_r = 500 * tex.screen_scale

            position = (BOX_CENTER - center_offset) + (base_spacing * offset)
            if position == BOX_CENTER - center_offset:
                position += center_offset
            elif position > BOX_CENTER - center_offset:
                position += side_offset_r
            else:
                position -= side_offset_l

            if item.box.position == float('inf'):
                item.box.position = position
                item.box.target_position = position
            else:
                item.box.target_position = position

    def draw_boxes(self, move_away_attribute: float, is_ura: bool, diff_fade_out_attribute: float):
        for item in self.items:
            box = item.box
            fade = 1.0
            if self.genre_bg and self.genre_bg.start_position <= box.position <= self.genre_bg.end_position_final:
                fade = self.genre_bg.box_fade_in.attribute
            if (-156 * tex.screen_scale) <= box.position <= (tex.screen_width + 144) * tex.screen_scale:
                if box.position <= (500 * tex.screen_scale):
                    box.draw(box.position - int(move_away_attribute), tex.skin_config["boxes"].y, is_ura, inner_fade_override=diff_fade_out_attribute, outer_fade_override=fade)
                else:
                    box.draw(box.position + int(move_away_attribute), tex.skin_config["boxes"].y, is_ura, inner_fade_override=diff_fade_out_attribute, outer_fade_override=fade)

    def mark_crowns_dirty_for_song(self, song_file: SongFile):
        """Mark directories as needing crown recalculation when a song's score changes"""
        song_path = song_file.path

        # Find all directories that contain this song and mark them as dirty
        for dir_key, content_items in self.directory_contents.items():
            for item in content_items:
                if isinstance(item, SongFile) and item.path == song_path:
                    self.crown_cache_dirty.add(dir_key)
                    break

    def navigate_left(self):
        """Move selection left with wrap-around"""
        if self.items:
            if self.items[0].box.move is not None and not self.items[0].box.move.is_finished:
                return
            self.selected_index = (self.selected_index - 1) % len(self.items)
            self.calculate_box_positions()
            logger.info(f"Moved Left to {self.items[self.selected_index].path}")

    def navigate_right(self):
        """Move selection right with wrap-around"""
        if self.items:
            if self.items[0].box.move is not None and not self.items[0].box.move.is_finished:
                return
            self.selected_index = (self.selected_index + 1) % len(self.items)
            self.calculate_box_positions()
            logger.info(f"Moved Right to {self.items[self.selected_index].path}")

    def skip_left(self):
        if self.items:
            self.selected_index = (self.selected_index - 10) % len(self.items)
            self.calculate_box_positions()
            logger.info(f"Skipped Left to {self.items[self.selected_index].path}")

    def skip_right(self):
        if self.items:
            self.selected_index = (self.selected_index + 10) % len(self.items)
            self.calculate_box_positions()
            logger.info(f"Skipped Right to {self.items[self.selected_index].path}")

    def get_current_item(self):
        """Get the currently selected item"""
        if self.items and 0 <= self.selected_index < len(self.items):
            return self.items[self.selected_index]
        raise Exception("No current item available")

    def reset_items(self):
        """Reset the items in the song select scene"""
        song = self.get_current_item()
        if isinstance(song.box, SongBox):
            if song.box.yellow_box is not None:
                song.box.yellow_box.create_anim()

    def add_recent(self):
        """Add the current song to the recent list"""
        song = self.get_current_item()
        if isinstance(song, Directory):
            return
        if self.recent_folder is None:
            return

        recents_path = self.recent_folder.path / 'song_list.txt'
        new_entry = f'{song.hash}|{song.tja.metadata.title["en"]}|{song.tja.metadata.subtitle["en"]}\n'
        existing_entries = []
        if recents_path.exists():
            with open(recents_path, 'r', encoding='utf-8-sig') as song_list:
                existing_entries = song_list.readlines()
        existing_entries = [entry for entry in existing_entries if not entry.startswith(f'{song.hash}|')]
        all_entries = [new_entry] + existing_entries
        recent_entries = all_entries[:25]
        with open(recents_path, 'w', encoding='utf-8-sig') as song_list:
            song_list.writelines(recent_entries)

        logger.info(f"Added Recent: {song.hash} {song.tja.metadata.title['en']} {song.tja.metadata.subtitle['en']}")

    def add_favorite(self) -> bool:
        """Add the current song to the favorites list"""
        song = self.get_current_item()
        if isinstance(song, Directory):
            return False
        if self.favorite_folder is None:
            return False
        favorites_path = self.favorite_folder.path / 'song_list.txt'
        lines = []
        if not Path(favorites_path).exists():
            Path(favorites_path).touch()
        with open(favorites_path, 'r', encoding='utf-8-sig') as song_list:
            for line in song_list:
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                hash, title, subtitle = line.split('|')
                if song.hash == hash or (song.tja.metadata.title['en'] == title and song.tja.metadata.subtitle['en'] == subtitle):
                    if not self.in_favorites:
                        return False
                else:
                    lines.append(line)
        if self.in_favorites:
            with open(favorites_path, 'w', encoding='utf-8-sig') as song_list:
                for line in lines:
                    song_list.write(line + '\n')
            logger.info(f"Removed Favorite: {song.hash} {song.tja.metadata.title['en']} {song.tja.metadata.subtitle['en']}")
        else:
            with open(favorites_path, 'a', encoding='utf-8-sig') as song_list:
                song_list.write(f'{song.hash}|{song.tja.metadata.title["en"]}|{song.tja.metadata.subtitle["en"]}\n')
            logger.info(f"Added Favorite: {song.hash} {song.tja.metadata.title['en']} {song.tja.metadata.subtitle['en']}")
        return True

navigator = FileNavigator()
