import logging
import pyray as ray

from libs.global_data import Difficulty, PlayerNum, reset_session
from libs.audio import audio
from libs.chara_2d import Chara2D
from libs.global_objects import AllNetIcon, CoinOverlay, Nameplate
from libs.screen import Screen
from libs.texture import tex
from libs.utils import (
    OutlinedText,
    get_current_ms,
    global_data,
    is_l_don_pressed,
    is_r_don_pressed
)
from scenes.game import ScoreMethod

logger = logging.getLogger(__name__)

class State:
    """Enum representing the state of the result screen."""
    FAIL = 0
    CLEAR = 1
    RAINBOW = 2

class ResultScreen(Screen):
    def on_screen_start(self):
        super().on_screen_start()
        self.song_info = OutlinedText(global_data.session_data[global_data.player_num].song_title, tex.skin_config["song_info_result"].font_size, ray.WHITE, outline_thickness=5)
        audio.play_sound('bgm', 'music')
        self.fade_in = FadeIn(global_data.player_num)
        self.fade_out = tex.get_animation(0)
        self.coin_overlay = CoinOverlay()
        self.allnet_indicator = AllNetIcon()
        self.start_ms = get_current_ms()
        self.is_skipped = False
        self.background = Background(global_data.player_num, tex.screen_width)
        self.player_1 = ResultPlayer(global_data.player_num, False, False)

    def on_screen_end(self, next_screen: str):
        global_data.songs_played += 1
        reset_session()
        return super().on_screen_end(next_screen)

    def handle_input(self):
        if is_r_don_pressed() or is_l_don_pressed():
            if not self.is_skipped:
                self.is_skipped = True
            else:
                self.fade_out.start()
            audio.play_sound('don', 'sound')

    def update(self):
        super().update()
        current_time = get_current_ms()
        self.fade_in.update(current_time)
        self.player_1.update(current_time, self.fade_in.is_finished, self.is_skipped)

        if current_time >= self.start_ms + 5000 and not self.fade_out.is_started:
            self.handle_input()

        self.fade_out.update(current_time)
        if self.fade_out.is_finished:
            self.fade_out.update(current_time)
            return self.on_screen_end("SONG_SELECT")

    def draw_overlay(self):
        self.fade_in.draw()
        ray.draw_rectangle(0, 0, tex.screen_width, tex.screen_height, ray.fade(ray.BLACK, self.fade_out.attribute))
        self.coin_overlay.draw()
        self.allnet_indicator.draw()

    def draw_song_info(self):
        tex.draw_texture('song_info', 'song_num', frame=global_data.songs_played%4)
        self.song_info.draw(outline_color=ray.BLACK, x=tex.skin_config["song_info_result"].x - self.song_info.texture.width, y=tex.skin_config["song_info_result"].y - self.song_info.texture.height / 2)

    def draw(self):
        self.background.draw()
        self.draw_song_info()
        self.player_1.draw()
        self.draw_overlay()


class Background:
    def __init__(self, player_num: PlayerNum, width: float):
        self.player_num = player_num
        self.width = width
    def draw(self):
        x = 0
        if self.player_num == 3:
            footer_height = tex.textures["background"]["footer_1p"].height
        else:
            footer_height = tex.textures["background"][f"footer_{self.player_num}p"].height
        if self.player_num == PlayerNum.TWO_PLAYER:
            while x < self.width:
                tex.draw_texture('background', 'background_1p', x=x, y=-(tex.screen_height//2))
                tex.draw_texture('background', 'background_2p', x=x, y=tex.screen_height//2)
                tex.draw_texture('background', 'footer_1p', x=x, y=-(footer_height//2))
                tex.draw_texture('background', 'footer_2p', x=x, y=tex.screen_height-(footer_height//2))
                x += tex.screen_width // 5
        else:
            while x < self.width:
                tex.draw_texture('background', f'background_{self.player_num}p', x=x, y=-(tex.screen_height//2))
                tex.draw_texture('background', f'background_{self.player_num}p', x=x, y=(tex.screen_height//2))
                tex.draw_texture('background', f'footer_{self.player_num}p', x=x, y=-(footer_height//2))
                tex.draw_texture('background', f'footer_{self.player_num}p', x=x, y=tex.screen_height-(footer_height//2))
                x += tex.screen_width // 5
        tex.draw_texture('background', 'result_text')

class ResultPlayer:
    def __init__(self, player_num: PlayerNum, has_2p: bool, is_2p: bool):
        self.player_num = player_num
        self.has_2p = has_2p
        self.is_2p = is_2p
        self.fade_in_finished = False
        self.fade_in_bottom = tex.get_animation(1, is_copy=True)
        self.bottom_characters = BottomCharacters()
        self.gauge = None
        self.score_delay = None
        self.crown = None
        self.state = None
        self.high_score_indicator = None
        self.chara = Chara2D(int(self.player_num) - 1)
        session_data = global_data.session_data[self.player_num]
        self.score_animator = ScoreAnimator(session_data.result_data.score)
        plate_info = global_data.config[f'nameplate_{self.player_num}p']
        self.nameplate = Nameplate(plate_info['name'], plate_info['title'], self.player_num, plate_info['dan'], plate_info['gold'], plate_info['rainbow'], plate_info['title_bg'])
        self.score, self.good, self.ok, self.bad, self.max_combo, self.total_drumroll = '', '', '', '', '', ''
        self.update_list: list[tuple[str, int]] = [('score', session_data.result_data.score),
            ('good', session_data.result_data.good),
            ('ok', session_data.result_data.ok),
            ('bad', session_data.result_data.bad),
            ('max_combo', session_data.result_data.max_combo),
            ('total_drumroll', session_data.result_data.total_drumroll)]
        self.update_index = 0
        if session_data.result_data.ok == 0 and session_data.result_data.bad == 0:
            self.crown_type = 'crown_dfc'
        elif session_data.result_data.bad == 0:
            self.crown_type = 'crown_fc'
        else:
            self.crown_type = 'crown_clear'

    def update_score_animation(self, is_skipped: bool):
        """
        Update the score animation if a high score is achieved.
        """
        if is_skipped:
            if self.update_index == len(self.update_list):
                return
            setattr(self, self.update_list[self.update_index][0], self.update_list[self.update_index][1])
            self.update_index += 1
        elif self.score_delay is not None:
            if get_current_ms() > self.score_delay:
                if self.score_animator is not None and not self.score_animator.is_finished:
                    curr_num = self.update_list[self.update_index][0]
                    setattr(self, self.update_list[self.update_index][0], self.score_animator.next_score())
                    if self.update_list[self.update_index] != curr_num:
                        audio.play_sound('num_up', 'sound')
                    if self.score_animator.is_finished:
                        audio.play_sound('don', 'sound')
                        self.score_delay += 750
                        if self.update_index == len(self.update_list) - 1:
                            self.is_skipped = True
                            return
                        self.update_index += 1
                        self.score_animator = ScoreAnimator(self.update_list[self.update_index][1])
                    self.score_delay += 16.67 * 3
        if self.update_index > 0 and self.high_score_indicator is None:
            session_data = global_data.session_data[self.player_num]
            if session_data.result_data.score > session_data.result_data.prev_score:
                self.high_score_indicator = HighScoreIndicator(session_data.result_data.prev_score, session_data.result_data.score, self.is_2p)

    def update(self, current_ms: float, fade_in_finished: bool, is_skipped: bool):
        self.fade_in_finished = fade_in_finished
        if self.fade_in_finished and self.gauge is None:
            self.gauge = Gauge(self.player_num, global_data.session_data[self.player_num].result_data.gauge_length, self.is_2p)
            self.bottom_characters.start()
        self.bottom_characters.update(self.state)
        self.update_score_animation(is_skipped)

        if self.bottom_characters.is_finished and self.crown is None:
            if self.gauge is not None and self.gauge.gauge_length > 69:
                self.crown = Crown(self.is_2p)

        if self.high_score_indicator is not None:
            self.high_score_indicator.update(current_ms)

        self.fade_in_bottom.update(current_ms)
        self.nameplate.update(current_ms)
        if self.gauge is not None:
            self.gauge.update(current_ms)
            if self.gauge.is_finished and self.score_delay is None:
                self.score_delay = current_ms + 1883

        if self.score_delay is not None:
            if current_ms > self.score_delay and not self.fade_in_bottom.is_started:
                self.fade_in_bottom.start()
                if self.gauge is not None:
                    self.state = self.gauge.state

        if self.crown is not None:
            self.crown.update(current_ms)

        self.chara.update(current_ms, 100, False, False)

    def draw_score_info(self):
        """Draw the score information."""
        for j, score in enumerate([self.good, self.ok, self.bad, self.max_combo, self.total_drumroll]):
            if score == '':
                continue
            score_str = str(score)[::-1]
            for i, digit in enumerate(score_str):
                tex.draw_texture('score', 'judge_num', frame=int(digit), x=-(i*tex.skin_config["score_info_counter_margin"].x), index=j+(self.is_2p*5))

    def draw_total_score(self):
        """
        Draw the total score.
        """
        if not self.fade_in_finished:
            return
        if global_data.config["general"]["score_method"] == ScoreMethod.SHINUCHI:
            tex.draw_texture('score', 'score_shinuchi', index=self.is_2p)
        else:
            tex.draw_texture('score', 'score', index=self.is_2p)
        if self.score != '':
            for i in range(len(str(self.score))):
                tex.draw_texture('score', 'score_num', x=-(i*tex.skin_config["result_score_margin"].x), frame=int(str(self.score)[::-1][i]), index=self.is_2p)

    def draw_modifiers(self):
        """Draw the modifiers if enabled."""
        if global_data.modifiers[self.player_num].display:
            tex.draw_texture('score', 'mod_doron', index=self.is_2p)
        if global_data.modifiers[self.player_num].inverse:
            tex.draw_texture('score', 'mod_abekobe', index=self.is_2p)
        if global_data.modifiers[self.player_num].random == 1:
            tex.draw_texture('score', 'mod_kimagure', index=self.is_2p)
        elif global_data.modifiers[self.player_num].random == 2:
            tex.draw_texture('score', 'mod_detarame', index=self.is_2p)
        if global_data.modifiers[self.player_num].speed >= 4:
            tex.draw_texture('score', 'mod_yonbai', index=self.is_2p)
        elif global_data.modifiers[self.player_num].speed >= 3:
            tex.draw_texture('score', 'mod_sanbai', index=self.is_2p)
        elif global_data.modifiers[self.player_num].speed > 1:
            tex.draw_texture('score', 'mod_baisaku', index=self.is_2p)

    def draw(self):
        if self.is_2p:
            if self.state == State.FAIL:
                tex.draw_texture('background', 'gradient_fail', fade=min(0.4, self.fade_in_bottom.attribute))
            elif self.state == State.CLEAR:
                tex.draw_texture('background', 'gradient_clear', fade=min(0.4, self.fade_in_bottom.attribute))
        else:
            y = tex.skin_config["result_2p_offset"].y if self.has_2p else 0
            if self.state == State.FAIL:
                tex.draw_texture('background', 'gradient_fail', fade=min(0.4, self.fade_in_bottom.attribute), y=y)
            elif self.state == State.CLEAR:
                tex.draw_texture('background', 'gradient_clear', fade=min(0.4, self.fade_in_bottom.attribute), y=y)
        tex.draw_texture('score', 'overlay', color=ray.fade(ray.WHITE, 0.75), index=self.is_2p)
        tex.draw_texture('score', 'difficulty', frame=global_data.session_data[self.player_num].selected_difficulty, index=self.is_2p)
        if not self.has_2p:
            self.bottom_characters.draw()

        tex.draw_texture('score', 'judge_good', index=self.is_2p)
        tex.draw_texture('score', 'judge_ok', index=self.is_2p)
        tex.draw_texture('score', 'judge_bad', index=self.is_2p)
        tex.draw_texture('score', 'max_combo', index=self.is_2p)
        tex.draw_texture('score', 'drumroll', index=self.is_2p)

        self.draw_score_info()
        self.draw_total_score()

        if self.crown is not None:
            self.crown.draw(self.crown_type)

        self.draw_modifiers()

        if self.high_score_indicator is not None:
            self.high_score_indicator.draw()

        self.chara.draw(y=tex.skin_config["result_chara"].y+(self.is_2p*tex.screen_height//2))
        if self.gauge is not None:
            self.gauge.draw()
        self.nameplate.draw(tex.skin_config["result_nameplate"].x, tex.skin_config["result_nameplate"].y+(self.is_2p*tex.skin_config["result_nameplate"].height))

class Crown:
    """Represents a crown animation"""
    def __init__(self, is_2p: bool):
        self.is_2p = is_2p
        self.resize = tex.get_animation(2, is_copy=True)
        self.resize_fix = tex.get_animation(3, is_copy=True)
        self.white_fadein = tex.get_animation(4, is_copy=True)
        self.gleam = tex.get_animation(5, is_copy=True)
        self.fadein = tex.get_animation(6, is_copy=True)
        self.resize.start()
        self.resize_fix.start()
        self.white_fadein.start()
        self.gleam.start()
        self.fadein.start()
        self.sound_played = False

    def update(self, current_ms: float):
        self.fadein.update(current_ms)
        self.resize.update(current_ms)
        self.resize_fix.update(current_ms)
        self.white_fadein.update(current_ms)
        self.gleam.update(current_ms)
        if self.resize_fix.is_finished and not self.sound_played:
            audio.play_sound('crown', 'sound')
            self.sound_played = True

    def draw(self, crown_name: str):
        scale = self.resize.attribute
        if self.resize.is_finished:
            scale = self.resize_fix.attribute
        tex.draw_texture('crown', crown_name, scale=scale, center=True, index=self.is_2p)
        tex.draw_texture('crown', 'crown_fade', fade=self.white_fadein.attribute, index=self.is_2p)
        if self.gleam.attribute >= 0:
            tex.draw_texture('crown', 'gleam', frame=self.gleam.attribute, index=self.is_2p)

class BottomCharacters:
    """Represents the bottom characters animation"""
    def __init__(self):
        self.move_up = tex.get_animation(7)
        self.move_down = tex.get_animation(8)
        self.bounce_up = tex.get_animation(9)
        self.bounce_down = tex.get_animation(10)
        self.move_center = tex.get_animation(11)
        self.c_bounce_up = tex.get_animation(12)
        self.c_bounce_down = tex.get_animation(13)
        self.flower_up = tex.get_animation(14)
        self.state = None
        self.flower_index = 0
        self.flower_start = None
        self.chara_0_index = 0
        self.chara_1_index = 0
        self.is_finished = False

    def start(self):
        self.move_up.start()
        self.move_down.start()
        self.c_bounce_up.start()
        self.c_bounce_down.start()

    def update(self, state):
        self.state = state
        if self.state == State.CLEAR or self.state == State.RAINBOW:
            self.chara_0_index = 1
            self.chara_1_index = 1
            if not self.bounce_up.is_started:
                self.bounce_up.start()
                self.bounce_down.start()
                self.move_center.start()
            if self.flower_start is None:
                self.flower_up.start()
                self.flower_start = get_current_ms()
        elif self.state == State.FAIL:
            self.chara_0_index = 2
            self.chara_1_index = 2

        self.move_up.update(get_current_ms())
        self.move_down.update(get_current_ms())
        self.is_finished = self.move_down.is_finished
        self.bounce_up.update(get_current_ms())
        self.bounce_down.update(get_current_ms())
        if self.bounce_down.is_finished:
            self.bounce_up.restart()
            self.bounce_down.restart()
        self.move_center.update(get_current_ms())
        self.flower_up.update(get_current_ms())

        if self.flower_start is not None:
            if get_current_ms() > self.flower_start + 116*2 + 333:
                self.flower_index = 2
            elif get_current_ms() > self.flower_start + 116 + 333:
                self.flower_index = 1

        self.c_bounce_up.update(get_current_ms())
        self.c_bounce_down.update(get_current_ms())
        if self.c_bounce_down.is_finished:
            self.c_bounce_up.restart()
            self.c_bounce_down.restart()

    def draw_flowers(self):
        tex.draw_texture('bottom','flowers', y=-self.flower_up.attribute, frame=self.flower_index)
        tex.draw_texture('bottom','flowers', y=-self.flower_up.attribute, frame=self.flower_index, x=tex.skin_config["result_flowers_offset"].x, mirror='horizontal')

    def draw(self):
        self.draw_flowers()

        y = -self.move_up.attribute + self.move_down.attribute + self.bounce_up.attribute - self.bounce_down.attribute
        if self.state == State.RAINBOW:
            center_y = self.c_bounce_up.attribute - self.c_bounce_down.attribute
            tex.draw_texture('bottom', 'chara_center', y=-self.move_center.attribute + center_y)

        tex.draw_texture('bottom', 'chara_0', frame=self.chara_0_index, y=y)
        tex.draw_texture('bottom', 'chara_1', frame=self.chara_1_index, y=y)

class FadeIn:
    """A fade out disguised as a fade in"""
    def __init__(self, player_num: PlayerNum):
        self.fadein = tex.get_animation(15)
        self.fadein.start()
        self.is_finished = False
        self.player_num = player_num

    def update(self, current_ms: float):
        self.fadein.update(current_ms)
        self.is_finished = self.fadein.is_finished

    def draw(self):
        x = 0
        footer_height = tex.textures["background"]["footer_1p"].height
        if self.player_num == PlayerNum.TWO_PLAYER:
            while x < tex.screen_width:
                tex.draw_texture('background', 'background_1p', x=x, y=-tex.screen_height//2, fade=self.fadein.attribute)
                tex.draw_texture('background', 'background_2p', x=x, y=tex.screen_height//2, fade=self.fadein.attribute)
                tex.draw_texture('background', 'footer_1p', x=x, y=-footer_height, fade=self.fadein.attribute)
                tex.draw_texture('background', 'footer_2p', x=x, y=tex.screen_height - footer_height, fade=self.fadein.attribute)
                x += tex.screen_width // 5
        else:
            while x < tex.screen_width:
                tex.draw_texture('background', f'background_{self.player_num}p', x=x, y=-tex.screen_height//2, fade=self.fadein.attribute)
                tex.draw_texture('background', f'background_{self.player_num}p', x=x, y=tex.screen_height//2, fade=self.fadein.attribute)
                tex.draw_texture('background', f'footer_{self.player_num}p', x=x, y=-footer_height, fade=self.fadein.attribute)
                tex.draw_texture('background', f'footer_{self.player_num}p', x=x, y=tex.screen_height - footer_height, fade=self.fadein.attribute)
                x += tex.screen_width // 5

class ScoreAnimator:
    """Animates a number from left to right"""
    def __init__(self, target_score):
        self.target_score = str(target_score)
        self.current_score_list = [[0,0] for _ in range(len(self.target_score))]
        self.digit_index = len(self.target_score) - 1
        self.is_finished = False

    def next_score(self) -> str:
        """Returns the next number in the animation"""
        if self.digit_index == -1:
            self.is_finished = True
            return str(int(''.join([str(item[0]) for item in self.current_score_list])))
        curr_digit, counter = self.current_score_list[self.digit_index]
        if counter < 9:
            self.current_score_list[self.digit_index][1] += 1
            self.current_score_list[self.digit_index][0] = (curr_digit + 1) % 10
        else:
            self.current_score_list[self.digit_index][0] = int(self.target_score[self.digit_index])
            self.digit_index -= 1
        ret_val = ''.join([str(item[0]) for item in self.current_score_list])
        if int(ret_val) == 0:
            if not (len(self.target_score) - self.digit_index) > (len(self.target_score)):
                return '0' * (len(self.target_score) - self.digit_index)
            return '0'
        return str(int(ret_val))

class HighScoreIndicator:
    """Indicates the difference between the old and new high score"""
    def __init__(self, old_score: int, new_score: int, is_2p: bool):
        self.is_2p = is_2p
        self.score_diff = new_score - old_score
        self.move = tex.get_animation(18)
        self.fade = tex.get_animation(19)
        self.move.start()
        self.fade.start()

    def update(self, current_ms):
        self.move.update(current_ms)
        self.fade.update(current_ms)

    def draw(self):
        tex.draw_texture('score', 'high_score', y=self.move.attribute, fade=self.fade.attribute, index=self.is_2p)
        for i in range(len(str(self.score_diff))):
            tex.draw_texture('score', 'high_score_num', x=-(i*tex.skin_config['high_score_indicator_margin'].x), frame=int(str(self.score_diff)[::-1][i]), y=self.move.attribute, fade=self.fade.attribute, index=self.is_2p)


class Gauge:
    """The gauge from the game screen, at 0.9x scale"""
    def __init__(self, player_num: PlayerNum, gauge_length: float, is_2p: bool):
        self.is_2p = is_2p
        self.player_num = player_num
        self.difficulty = min(Difficulty.HARD, global_data.session_data[player_num].selected_difficulty)
        self.gauge_length = gauge_length
        self.clear_start = [69, 69, 69]
        self.gauge_max = 87
        if self.difficulty >= Difficulty.HARD:
            self.string_diff = "_hard"
        elif self.difficulty == Difficulty.NORMAL:
            self.string_diff = "_normal"
        elif self.difficulty == Difficulty.EASY:
            self.string_diff = "_easy"
        self.rainbow_animation = tex.get_animation(16)
        self.gauge_fade_in = tex.get_animation(17)
        self.tamashii_fire_change = tex.get_animation(20)
        self.rainbow_animation.start()
        self.gauge_fade_in.start()
        self.is_finished = self.gauge_fade_in.is_finished
        if self.gauge_length == self.gauge_max:
            self.state = State.RAINBOW
        elif self.gauge_length >= self.clear_start[self.difficulty] - 1:
            self.state = State.CLEAR
        else:
            self.state = State.FAIL

    def update(self, current_ms: float):
        self.rainbow_animation.update(current_ms)
        self.tamashii_fire_change.update(current_ms)
        if self.rainbow_animation.is_finished:
            self.rainbow_animation.restart()
        self.gauge_fade_in.update(current_ms)
        self.is_finished = self.gauge_fade_in.is_finished

    def draw(self):
        scale = 10/11
        tex.draw_texture('gauge', f'{self.player_num}p_unfilled' + self.string_diff, scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
        gauge_length = int(self.gauge_length)
        bar_width = tex.textures["gauge"][f"{self.player_num}p_bar"].width
        if gauge_length == self.gauge_max:
            if 0 < self.rainbow_animation.attribute < 8:
                tex.draw_texture('gauge', 'rainbow'  + self.string_diff, frame=self.rainbow_animation.attribute-1, scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
            tex.draw_texture('gauge', 'rainbow'  + self.string_diff, frame=self.rainbow_animation.attribute, scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
        else:
            tex.draw_texture('gauge', f'{self.player_num}p_bar', x2=(gauge_length*bar_width)-(bar_width*6), scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
            if gauge_length >= self.clear_start[self.difficulty] - 1:
                tex.draw_texture('gauge', 'bar_clear_transition', x=(self.clear_start[self.difficulty]*bar_width)-(bar_width*7), scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
                tex.draw_texture('gauge', 'bar_clear_top', x=(self.clear_start[self.difficulty]*bar_width)-(bar_width*6), x2=(gauge_length - self.clear_start[self.difficulty])*bar_width, scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
                tex.draw_texture('gauge', 'bar_clear_bottom', x=(self.clear_start[self.difficulty]*bar_width)-(bar_width*6), x2=(gauge_length - self.clear_start[self.difficulty])*bar_width, scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
        tex.draw_texture('gauge', 'overlay' + self.string_diff, scale=scale, fade=min(0.15, self.gauge_fade_in.attribute), index=self.is_2p)
        tex.draw_texture('gauge', 'footer', scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)

        if gauge_length >= self.clear_start[self.difficulty] - 1:
            tex.draw_texture('gauge', 'clear', scale=scale, fade=self.gauge_fade_in.attribute, index=self.difficulty+(self.is_2p*3))
            if self.state == State.RAINBOW:
                tex.draw_texture('gauge', 'tamashii_fire', scale=0.75 * scale, center=True, frame=self.tamashii_fire_change.attribute, fade=self.gauge_fade_in.attribute, index=self.is_2p)
            tex.draw_texture('gauge', 'tamashii', scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
            if self.state == State.RAINBOW and self.tamashii_fire_change.attribute in (0, 1, 4, 5):
                tex.draw_texture('gauge', 'tamashii_overlay', scale=scale, fade=min(0.5, self.gauge_fade_in.attribute), index=self.is_2p)
        else:
            tex.draw_texture('gauge', 'clear_dark', scale=scale, fade=self.gauge_fade_in.attribute, index=self.difficulty+(self.is_2p*3))
            tex.draw_texture('gauge', 'tamashii_dark', scale=scale, fade=self.gauge_fade_in.attribute, index=self.is_2p)
