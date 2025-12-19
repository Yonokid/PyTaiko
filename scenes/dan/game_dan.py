import copy
from typing import Optional, override
import pyray as ray
import logging
from libs.animation import Animation
from libs.audio import audio
from libs.background import Background
from libs.file_navigator import Exam
from libs.global_data import DanResultExam, DanResultSong, PlayerNum, global_data
from libs.global_objects import AllNetIcon
from libs.tja import TJAParser
from libs.transition import Transition
from libs.utils import OutlinedText, get_current_ms
from libs.texture import tex
from scenes.game import ClearAnimation, FCAnimation, FailAnimation, GameScreen, Gauge, ResultTransition, SongInfo

logger = logging.getLogger(__name__)

class DanGameScreen(GameScreen):
    JUDGE_X = 414

    @override
    def on_screen_start(self):
        self.mask_shader = ray.load_shader("shader/outline.vs", "shader/mask.fs")
        self.current_ms = 0
        self.end_ms = 0
        self.start_delay = 4000
        self.song_started = False
        self.song_music = None
        self.song_index = 0
        tex.unload_textures()
        tex.load_screen_textures('game')
        audio.load_screen_sounds('game')
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
        self.hori_name = OutlinedText(global_data.session_data[global_data.player_num].song_title, tex.skin_config["dan_title"].font_size, ray.WHITE)
        self.init_dan()
        self.background = Background(global_data.player_num, self.bpm, scene_preset='DAN')
        self.transition = Transition('', '', is_second=True)
        self.transition.start()
        self.dan_transition = DanTransition()
        self.dan_transition.start()
        self.allnet_indicator = AllNetIcon()
        self.result_transition = ResultTransition(PlayerNum.DAN)
        self.load_hitsounds()

    def init_dan(self):
        session_data = global_data.session_data[global_data.player_num]
        songs = copy.deepcopy(session_data.selected_dan)
        self.exams = copy.deepcopy(session_data.selected_dan_exam)
        self.total_notes = 0
        for song, genre_index, difficulty, level in songs:
            notes, branch_m, branch_e, branch_n = song.notes_to_position(difficulty)
            self.total_notes += sum(1 for note in notes.play_notes if note.type < 5)
            for branch in branch_m:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)
            for branch in branch_e:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)
            for branch in branch_n:
                self.total_notes += sum(1 for note in branch.play_notes if note.type < 5)
        song, genre_index, difficulty, level = songs[self.song_index]
        session_data.selected_difficulty = difficulty
        self.init_tja(song.file_path)
        self.color = session_data.dan_color
        self.player_1.is_dan = True
        self.player_1.gauge = DanGauge(global_data.player_num, self.total_notes)
        self.song_info = SongInfo(song.metadata.title.get(global_data.config["general"]["language"], "en"), genre_index)
        self.bpm = self.tja.metadata.bpm
        logger.info(f"TJA initialized for song: {song.file_path}")


        self.dan_info_cache = None
        self.exam_failed = [False] * len(self.exams)

    def change_song(self):
        session_data = global_data.session_data[global_data.player_num]
        songs = session_data.selected_dan
        song, genre_index, difficulty, level = songs[self.song_index]
        session_data.selected_difficulty = difficulty
        self.player_1.difficulty = difficulty
        self.tja = TJAParser(song.file_path, start_delay=self.start_delay)
        if self.song_music is not None:
            audio.unload_music_stream(self.song_music)
        self.song_music = None
        self.song_started = False

        if self.tja.metadata.wave.exists() and self.tja.metadata.wave.is_file() and self.song_music is None:
            self.song_music = audio.load_music_stream(self.tja.metadata.wave, 'song')
        self.player_1.tja = self.tja
        self.player_1.reset_chart()
        self.dan_transition.start()
        self.song_info = SongInfo(self.tja.metadata.title.get(global_data.config["general"]["language"], "en"), genre_index)
        self.start_ms = (get_current_ms() - self.tja.metadata.offset*1000)

    def _calculate_dan_info(self):
        """Calculate all dan info data for drawing"""
        remaining_notes = self.total_notes - self.player_1.good_count - self.player_1.ok_count - self.player_1.bad_count

        exam_data = []
        for exam in self.exams:
            progress_value = self._get_exam_progress(exam)
            progress = progress_value / exam.red

            if exam.range == 'less':
                progress = 1 - progress
                counter_value = max(0, exam.red - progress_value)
            elif exam.range == 'more':
                counter_value = max(0, progress_value)
            else:
                counter_value = max(0, progress_value)

            # Clamp progress
            progress = max(0, min(progress, 1))

            # Determine progress bar texture
            if progress == 1:
                bar_texture = 'exam_max'
            elif progress >= 0.5:
                bar_texture = 'exam_gold'
            else:
                bar_texture = 'exam_red'

            exam_data.append({
                'exam': exam,
                'progress': progress,
                'bar_texture': bar_texture,
                'counter_value': counter_value,
                'red_value': exam.red
            })

        return {
            'remaining_notes': remaining_notes,
            'exam_data': exam_data
        }

    def _get_exam_progress(self, exam: Exam) -> int:
        """Get progress value based on exam type"""
        type_mapping = {
            'gauge': (self.player_1.gauge.gauge_length / self.player_1.gauge.gauge_max) * 100,
            'judgeperfect': self.player_1.good_count,
            'judgegood': self.player_1.ok_count + self.player_1.bad_count,
            'judgebad': self.player_1.bad_count,
            'hit': self.player_1.good_count + self.player_1.ok_count + self.player_1.total_drumroll,
            'score': self.player_1.score,
            'combo': self.player_1.max_combo
        }
        return int(type_mapping.get(exam.type, 0))

    @override
    def global_keys(self):
        if ray.is_key_pressed(global_data.config["keys"]["restart_key"]):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
                audio.seek_music_stream(self.song_music, 0)
                self.song_started = False
            audio.play_sound('restart', 'sound')
            self.init_dan()

        if ray.is_key_pressed(global_data.config["keys"]["back_key"]):
            if self.song_music is not None:
                audio.stop_music_stream(self.song_music)
            return self.on_screen_end('DAN_SELECT')

    @override
    def spawn_ending_anims(self):
        if sum(song.bad for song in global_data.session_data[global_data.player_num].dan_result_data.songs) == 0:
            self.player_1.ending_anim = FCAnimation(self.player_1.is_2p)
        if self.player_1.gauge.is_clear and not any(self.exam_failed):
            self.player_1.ending_anim = ClearAnimation(self.player_1.is_2p)
        elif not self.player_1.gauge.is_clear:
            self.player_1.ending_anim = FailAnimation(self.player_1.is_2p)

    @override
    def update(self):
        super(GameScreen, self).update()
        current_time = get_current_ms()
        self.transition.update(current_time)
        self.current_ms = current_time - self.start_ms
        self.dan_transition.update(current_time)
        if self.transition.is_finished and self.dan_transition.is_finished:
            self.start_song(self.current_ms)
        else:
            self.start_ms = current_time - self.tja.metadata.offset*1000
        self.update_background(current_time)

        if self.song_music is not None:
            audio.update_music_stream(self.song_music)

        self.player_1.update(self.current_ms, current_time, self.background)
        self.song_info.update(current_time)
        self.result_transition.update(current_time)

        self.dan_info_cache = self._calculate_dan_info()
        self._check_exam_failures()

        if self.result_transition.is_finished and not audio.is_sound_playing('dan_transition'):
            logger.info("Result transition finished, moving to RESULT screen")
            return self.on_screen_end('DAN_RESULT')
        elif self.current_ms >= self.player_1.end_time + 1000:
            session_data = global_data.session_data[global_data.player_num]
            if len(session_data.selected_dan) > len(session_data.dan_result_data.songs):
                song_info = DanResultSong()
                song_info.song_title = self.song_info.song_name
                song_info.genre_index = session_data.selected_dan[self.song_index][1]
                song_info.selected_difficulty = session_data.selected_dan[self.song_index][2]
                song_info.diff_level = session_data.selected_dan[self.song_index][3]
                prev_good_count = sum(song.good for song in session_data.dan_result_data.songs)
                prev_ok_count = sum(song.ok for song in session_data.dan_result_data.songs)
                prev_bad_count = sum(song.bad for song in session_data.dan_result_data.songs)
                prev_drumroll_count = sum(song.drumroll for song in session_data.dan_result_data.songs)
                song_info.good = self.player_1.good_count - prev_good_count
                song_info.ok = self.player_1.ok_count - prev_ok_count
                song_info.bad = self.player_1.bad_count - prev_bad_count
                song_info.drumroll = self.player_1.total_drumroll - prev_drumroll_count
                session_data.dan_result_data.songs.append(song_info)
            if self.song_index == len(session_data.selected_dan) - 1:
                if self.end_ms != 0:
                    if current_time >= self.end_ms + 1000:
                        session_data.dan_result_data.dan_color = self.color
                        session_data.dan_result_data.dan_title = self.hori_name.text
                        session_data.dan_result_data.score = self.player_1.score
                        session_data.dan_result_data.gauge_length = self.player_1.gauge.gauge_length
                        session_data.dan_result_data.max_combo = self.player_1.max_combo
                        session_data.dan_result_data.exams = self.exams
                        for i in range(len(self.exams)):
                            exam_data = DanResultExam()
                            exam_data.bar_texture = self.dan_info_cache["exam_data"][i]["bar_texture"]
                            exam_data.counter_value = self.dan_info_cache["exam_data"][i]["counter_value"]
                            exam_data.failed = self.exam_failed[i]
                            exam_data.progress = self.dan_info_cache["exam_data"][i]["progress"]
                            session_data.dan_result_data.exam_data.append(exam_data)
                        if self.player_1.ending_anim is None:
                            self.spawn_ending_anims()
                    if current_time >= self.end_ms + 8533.34:
                        if not self.result_transition.is_started:
                            self.result_transition.start()
                            audio.play_sound('dan_transition', 'voice')
                            logger.info("Result transition started and voice played")
                else:
                    self.end_ms = current_time
            else:
                self.song_index += 1
                self.dan_transition.start()
                self.change_song()

        return self.global_keys()

    def _check_exam_failures(self):
        for i, exam in enumerate(self.exams):
            progress_value = self._get_exam_progress(exam)

            if self.exam_failed[i]:
                continue

            if exam.range == 'more':
                if progress_value < exam.red and self.end_ms != 0:
                    self.exam_failed[i] = True
                    audio.play_sound('exam_failed', 'sound')
                    logger.info(f"Exam {i} ({exam.type}) failed: {progress_value} < {exam.red}")
            elif exam.range == 'less':
                counter_value = max(0, exam.red - progress_value)
                if counter_value == 0:
                    self.exam_failed[i] = True
                    audio.play_sound('dan_failed', 'sound')
                    logger.info(f"Exam {i} ({exam.type}) failed: counter reached 0")

    def draw_dan_info(self):
        if self.dan_info_cache is None:
            return

        cache = self.dan_info_cache

        # Draw total notes counter
        tex.draw_texture('dan_info', 'total_notes')
        counter = str(cache['remaining_notes'])
        self._draw_counter(counter, margin=tex.skin_config["dan_total_notes_margin"].x, texture='total_notes_counter')

        # Draw exam info
        for i, exam_info in enumerate(cache['exam_data']):
            y_offset = i * tex.skin_config["dan_exam_info"].y
            exam = exam_info['exam']

            tex.draw_texture('dan_info', 'exam_bg', y=y_offset)
            tex.draw_texture('dan_info', 'exam_overlay_1', y=y_offset)

            # Draw progress bar
            tex.draw_texture('dan_info', exam_info['bar_texture'], x2=tex.skin_config["dan_exam_info"].width*exam_info['progress'], y=y_offset)

            # Draw exam type and red value counter
            red_counter = str(exam_info['red_value'])
            self._draw_counter(red_counter, margin=tex.skin_config["dan_score_box_margin"].x, texture='value_counter', index=0, y=y_offset, exam_type=exam.type)
            tex.draw_texture('dan_info', f'exam_{exam.type}', y=y_offset, x=-len(red_counter)*(20 * tex.screen_scale))

            # Draw range indicator
            if exam.range == 'less':
                tex.draw_texture('dan_info', 'exam_less', y=y_offset)
            elif exam.range == 'more':
                tex.draw_texture('dan_info', 'exam_more', y=y_offset)

            # Draw current value counter
            tex.draw_texture('dan_info', 'exam_overlay_2', y=y_offset)
            value_counter = str(exam_info['counter_value'])
            self._draw_counter(value_counter, margin=tex.skin_config["dan_score_box_margin"].x, texture='value_counter', index=1, y=y_offset)

            if exam.type == 'gauge':
                tex.draw_texture('dan_info', 'exam_percent', y=y_offset, index=0)
                tex.draw_texture('dan_info', 'exam_percent', y=y_offset, index=1)

            if self.exam_failed[i]:
                tex.draw_texture('dan_info', 'exam_bg', fade=0.5, y=y_offset)
                tex.draw_texture('dan_info', 'exam_failed', y=y_offset)

        # Draw frame and title
        tex.draw_texture('dan_info', 'frame', frame=self.color)
        if self.hori_name is not None:
            self.hori_name.draw(outline_color=ray.BLACK, x=tex.skin_config["dan_game_hori_name"].x - (self.hori_name.texture.width//2),
                               y=tex.skin_config["dan_game_hori_name"].y, x2=min(self.hori_name.texture.width, tex.skin_config["dan_game_hori_name"].width)-self.hori_name.texture.width)

    def _draw_counter(self, counter: str, margin: float, texture: str, index: Optional[int] = None, y: float = 0, exam_type: Optional[str] = None):
        """Helper to draw digit counters"""
        for j in range(len(counter)):
            kwargs = {'frame': int(counter[j]), 'x': -(len(counter) - j) * margin, 'y': y}
            if index is not None:
                kwargs['index'] = index
            if exam_type == 'gauge':
                # Add space for percentage
                kwargs['x'] = kwargs['x'] - margin
            tex.draw_texture('dan_info', texture, **kwargs)

    @override
    def draw(self):
        self.background.draw()
        self.draw_dan_info()
        self.player_1.draw(self.current_ms, self.start_ms, self.mask_shader, dan_transition=self.dan_transition)
        self.draw_overlay()


class DanTransition:
    def __init__(self):
        self.move = tex.get_animation(26)
        self.is_finished = False

    def start(self):
        self.move.start()
        self.is_finished = False

    def update(self, current_time):
        self.move.update(current_time)
        self.is_finished = self.move.is_finished

    def draw(self):
        tex.draw_texture('dan', 'transition', index=0, x=self.move.attribute, mirror='horizontal')
        tex.draw_texture('dan', 'transition', index=1, x=-self.move.attribute)


class DanGauge(Gauge):
    """The player's gauge"""
    def __init__(self, player_num: PlayerNum, total_notes: int):
        self.player_num = player_num
        self.string_diff = "_hard"
        self.gauge_length = 0
        self.previous_length = 0
        self.visual_length = 0
        self.total_notes = total_notes
        self.gauge_max = 89
        self.tamashii_fire_change = tex.get_animation(25)
        self.is_clear = False
        self.is_rainbow = False
        self.gauge_update_anim = tex.get_animation(10)
        self.rainbow_fade_in = None
        self.rainbow_animation = None

    def add_good(self):
        """Adds a good note to the gauge"""
        self.gauge_update_anim.start()
        self.previous_length = int(self.gauge_length)
        self.gauge_length += (1 / (self.total_notes * (self.gauge_max / 100))) * 100
        if self.gauge_length > self.gauge_max:
            self.gauge_length = self.gauge_max

        if int(self.gauge_length * 8) % 8 == 0:
            self.visual_length = int(self.gauge_length * tex.textures["gauge_dan"][f'{self.player_num}p_bar'].width)

    def add_ok(self):
        """Adds an ok note to the gauge"""
        self.gauge_update_anim.start()
        self.previous_length = int(self.gauge_length)
        self.gauge_length += (0.5 / (self.total_notes * (self.gauge_max / 100))) * 100
        if self.gauge_length > self.gauge_max:
            self.gauge_length = self.gauge_max

        if int(self.gauge_length * 8) % 8 == 0:
            self.visual_length = int(self.gauge_length * tex.textures["gauge_dan"][f'{self.player_num}p_bar'].width)

    def add_bad(self):
        """Adds a bad note to the gauge"""
        self.previous_length = int(self.gauge_length)
        self.gauge_length -= (2 / (self.total_notes * (self.gauge_max / 100))) * 100
        if self.gauge_length < 0:
            self.gauge_length = 0

        if int(self.gauge_length * 8) % 8 == 0:
            self.visual_length = int(self.gauge_length * tex.textures["gauge_dan"][f'{self.player_num}p_bar'].width)

    def update(self, current_ms: float):
        self.is_rainbow = self.gauge_length == self.gauge_max
        self.is_clear = self.is_rainbow
        if self.gauge_length == self.gauge_max and self.rainbow_fade_in is None:
            self.rainbow_fade_in = Animation.create_fade(450, initial_opacity=0.0, final_opacity=1.0)
            self.rainbow_fade_in.start()
        self.gauge_update_anim.update(current_ms)
        self.tamashii_fire_change.update(current_ms)

        if self.rainbow_fade_in is not None:
            self.rainbow_fade_in.update(current_ms)

        if self.rainbow_animation is None:
            self.rainbow_animation = Animation.create_texture_change((16.67*8) * 3, textures=[((16.67 * 3) * i, (16.67 * 3) * (i + 1), i) for i in range(8)])
            self.rainbow_animation.start()
        else:
            self.rainbow_animation.update(current_ms)
            if self.rainbow_animation.is_finished or self.gauge_length < 87:
                self.rainbow_animation = None

    def draw(self):
        tex.draw_texture('gauge_dan', 'border')
        tex.draw_texture('gauge_dan', f'{self.player_num}p_unfilled')
        tex.draw_texture('gauge_dan', f'{self.player_num}p_bar', x2=self.visual_length-8)

        # Rainbow effect for full gauge
        if self.gauge_length == self.gauge_max and self.rainbow_fade_in is not None and self.rainbow_animation is not None:
            if 0 < self.rainbow_animation.attribute < 8:
                tex.draw_texture('gauge_dan', 'rainbow', frame=self.rainbow_animation.attribute-1, fade=self.rainbow_fade_in.attribute)
            tex.draw_texture('gauge_dan', 'rainbow', frame=self.rainbow_animation.attribute, fade=self.rainbow_fade_in.attribute)
        if self.gauge_update_anim is not None and self.visual_length <= self.gauge_max and self.visual_length > self.previous_length:
            tex.draw_texture('gauge_dan', f'{self.player_num}p_bar_fade', x=self.visual_length-8, fade=self.gauge_update_anim.attribute)
        tex.draw_texture('gauge_dan', 'overlay', fade=0.15)

        # Draw clear status indicators
        if self.is_rainbow:
            tex.draw_texture('gauge_dan', 'tamashii_fire', scale=0.75, center=True, frame=self.tamashii_fire_change.attribute)
            tex.draw_texture('gauge_dan', 'tamashii')
            if self.is_rainbow and self.tamashii_fire_change.attribute in (0, 1, 4, 5):
                tex.draw_texture('gauge_dan', 'tamashii_overlay', fade=0.5)
        else:
            tex.draw_texture('gauge_dan', 'tamashii_dark')
