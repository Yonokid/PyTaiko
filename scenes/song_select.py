import random
from dataclasses import fields
from pathlib import Path

import pyray as ray
import logging

from libs.file_navigator import BackBox, DanCourse, navigator
from libs.audio import audio
from libs.chara_2d import Chara2D
from libs.file_navigator import Directory, SongBox, SongFile
from libs.global_data import Difficulty, Modifiers, PlayerNum
from libs.global_objects import AllNetIcon, CoinOverlay, Nameplate, Indicator, Timer
from libs.screen import Screen
from libs.texture import tex
from libs.transition import Transition
from libs.utils import (
    OutlinedText,
    get_current_ms,
    global_data,
    is_l_don_pressed,
    is_l_kat_pressed,
    is_r_don_pressed,
    is_r_kat_pressed,
)

logger = logging.getLogger(__name__)

class State:
    BROWSING = 0
    SONG_SELECTED = 1
    DIFF_SORTING = 2

class SongSelectScreen(Screen):
    BOX_CENTER = 444
    def on_screen_start(self):
        super().on_screen_start()
        audio.set_sound_volume('ura_switch', 0.25)
        audio.set_sound_volume('add_favorite', 3.0)
        audio.play_sound('bgm', 'music')
        audio.play_sound('voice_enter', 'voice')
        self.navigator = navigator
        self.background_move = tex.get_animation(0)
        self.move_away = tex.get_animation(1)
        self.diff_fade_out = tex.get_animation(2)
        self.text_fade_out = tex.get_animation(3)
        self.text_fade_in = tex.get_animation(4)
        self.background_fade_change = tex.get_animation(5)
        self.blue_arrow_fade = tex.get_animation(29)
        self.blue_arrow_move = tex.get_animation(30)
        self.blue_arrow_fade.start()
        self.blue_arrow_move.start()
        self.state = State.BROWSING
        self.game_transition = None
        self.demo_song = None
        self.diff_sort_selector = None
        self.coin_overlay = CoinOverlay()
        self.allnet_indicator = AllNetIcon()
        self.indicator = Indicator(Indicator.State.SELECT)
        self.texture_index = SongBox.DEFAULT_INDEX
        self.last_texture_index = SongBox.DEFAULT_INDEX
        self.last_moved = get_current_ms()
        self.timer_browsing = Timer(100, get_current_ms(), self.navigator.select_current_item)
        self.timer_selected = Timer(40, get_current_ms(), self._confirm_selection_wrapper)
        self.screen_init = True
        self.ura_switch_animation = UraSwitchAnimation()
        self.dan_transition = DanTransition()

        session_data = global_data.session_data[global_data.player_num]
        self.player_1 = SongSelectPlayer(global_data.player_num, self.text_fade_in)

        if self.navigator.items == []:
            logger.warning("No navigator items found, returning to ENTRY screen")
            return self.on_screen_end("ENTRY")

        if str(session_data.selected_song) in self.navigator.all_song_files:
            selected_song = self.navigator.all_song_files[str(session_data.selected_song)]
            if not isinstance(selected_song, DanCourse):
                self.navigator.mark_crowns_dirty_for_song(selected_song)

        curr_item = self.navigator.get_current_item()
        if isinstance(curr_item, SongFile):
            curr_item.box.get_scores()
        self.navigator.add_recent()

    def finalize_song(self, current_item: SongFile):
        global_data.session_data[global_data.player_num].selected_song = current_item.path
        global_data.session_data[global_data.player_num].song_hash = global_data.song_hashes[current_item.hash][0]["diff_hashes"][self.player_1.selected_difficulty]
        global_data.session_data[global_data.player_num].selected_difficulty = self.player_1.selected_difficulty
        global_data.session_data[global_data.player_num].genre_index = current_item.box.name_texture_index

    def on_screen_end(self, next_screen):
        self.screen_init = False
        self.reset_demo_music()
        current_item = self.navigator.get_current_item()
        if isinstance(current_item, SongFile):
            self.finalize_song(current_item)
        self.player_1.nameplate.unload()
        if isinstance(current_item.box, SongBox) and current_item.box.yellow_box is not None:
            current_item.box.yellow_box.create_anim()
        return super().on_screen_end(next_screen)

    def reset_demo_music(self):
        """Reset the preview music to the song select bgm."""
        if self.demo_song is not None:
            audio.stop_music_stream(self.demo_song)
            audio.unload_music_stream(self.demo_song)
            audio.play_sound('bgm', 'music')
        self.demo_song = None
        self.navigator.get_current_item().box.wait = get_current_ms()

    def handle_input_browsing(self):
        """Handle input for browsing songs."""
        action = self.player_1.handle_input_browsing(self.last_moved, self.navigator.items[self.navigator.selected_index] if self.navigator.items else None)
        current_time = get_current_ms()
        if action == "skip_left":
            self.reset_demo_music()
            for _ in range(10):
                self.navigator.navigate_left()
            self.last_moved = current_time
        elif action == "skip_right":
            self.reset_demo_music()
            for _ in range(10):
                self.navigator.navigate_right()
            self.last_moved = current_time
        elif action == "navigate_left":
            self.reset_demo_music()
            self.navigator.navigate_left()
            self.last_moved = current_time
        elif action == "navigate_right":
            self.reset_demo_music()
            self.navigator.navigate_right()
            self.last_moved = current_time
        elif action == "go_back":
            self.navigator.go_back()
        elif action == "diff_sort":
            self.state = State.DIFF_SORTING
            self.diff_sort_selector = DiffSortSelect(self.navigator.diff_sort_statistics, self.navigator.diff_sort_diff, self.navigator.diff_sort_level)
            self.text_fade_in.start()
            self.text_fade_out.start()
        elif action == "select_song":
            current_song = self.navigator.get_current_item()
            if isinstance(current_song, Directory) and current_song.box.texture_index == 13:
                if len(self.navigator.directory_contents[str(current_song.path)]) == 0:
                    return
                self.dan_transition.start()
                audio.stop_sound('bgm')
                return
            selected_song = self.navigator.select_current_item()
            if isinstance(selected_song, SongFile):
                self.state = State.SONG_SELECTED
                self.player_1.on_song_selected(selected_song)
                audio.play_sound('don', 'sound')
                audio.play_sound('voice_select_diff', 'voice')
                self.move_away.start()
                self.diff_fade_out.start()
                self.text_fade_out.start()
                self.text_fade_in.start()
                self.player_1.selected_diff_bounce.start()
                self.player_1.selected_diff_fadein.start()
        elif action == "add_favorite":
            self.navigator.add_favorite()
            current_box = self.navigator.get_current_item().box
            if not isinstance(current_box, SongBox):
                return
            current_box.is_favorite = not current_box.is_favorite

    def handle_input_selected(self):
        """Handle input for selecting difficulty."""
        result = self.player_1.handle_input_selected(self.navigator.get_current_item())
        if result == "cancel":
            self._cancel_selection()
        elif result == "confirm":
            self._confirm_selection()
        elif result == "ura_toggle":
            self.ura_switch_animation.start(not self.player_1.is_ura)

    def handle_input_diff_sort(self):
        """
        Handle input for sorting difficulty.
        """
        if self.diff_sort_selector is None:
            raise Exception("Diff sort selector was not able to be created")

        result = self.player_1.handle_input_diff_sort(self.diff_sort_selector)

        if result is not None:
            diff, level = result
            self.diff_sort_selector = None
            self.state = State.BROWSING
            self.text_fade_out.reset()
            self.text_fade_in.reset()
            if diff != -1:
                if level != -1:
                    self.navigator.diff_sort_diff = diff
                    self.navigator.diff_sort_level = level
                self.navigator.select_current_item()

    def _cancel_selection(self):
        """Reset to browsing state"""
        self.player_1.selected_song = False
        self.move_away.reset()
        self.diff_fade_out.reset()
        self.text_fade_out.reset()
        self.text_fade_in.reset()
        self.state = State.BROWSING
        self.timer_browsing = Timer(100, get_current_ms(), self.navigator.select_current_item)
        self.timer_selected = Timer(40, get_current_ms(), self._confirm_selection_wrapper)
        self.navigator.reset_items()

    def _confirm_selection_wrapper(self):
        """Wrapper for timer callback"""
        self._confirm_selection()

    def _confirm_selection(self, player_selected: int = 1):
        """Confirm song selection and create game transition"""
        audio.play_sound('don', 'sound')
        audio.play_sound(f'voice_start_song_{global_data.player_num}p', 'voice')
        self.player_1.selected_diff_highlight_fade.start()
        self.player_1.selected_diff_text_resize.start()
        self.player_1.selected_diff_text_fadein.start()

    def handle_input(self):
        self.player_1.handle_input(self.state, self)

    def update_players(self, current_time) -> str:
        self.player_1.update(current_time)
        if self.text_fade_out.is_finished:
            self.player_1.selected_song = True
        next_screen = "GAME"
        return next_screen

    def check_for_selection(self):
        if self.player_1.selected_diff_highlight_fade.is_finished and not audio.is_sound_playing(f'voice_start_song_{global_data.player_num}p') and self.game_transition is None:
            selected_song = self.navigator.get_current_item()
            if not isinstance(selected_song, SongFile):
                raise Exception("picked directory")

            title = selected_song.tja.metadata.title.get(
                global_data.config['general']['language'], '')
            subtitle = selected_song.tja.metadata.subtitle.get(
                global_data.config['general']['language'], '')
            self.game_transition = Transition(title, subtitle)
            self.game_transition.start()

    def update(self):
        ret_val = super().update()
        if ret_val is not None:
            return ret_val
        current_time = get_current_ms()
        self.background_move.update(current_time)
        self.move_away.update(current_time)
        self.diff_fade_out.update(current_time)
        self.background_fade_change.update(current_time)
        self.text_fade_out.update(current_time)
        self.text_fade_in.update(current_time)
        self.ura_switch_animation.update(current_time)
        self.indicator.update(current_time)
        self.blue_arrow_fade.update(current_time)
        self.blue_arrow_move.update(current_time)
        self.dan_transition.update(current_time)
        if self.dan_transition.is_finished:
            self.navigator.select_current_item()
            return self.on_screen_end('DAN_SELECT')

        next_screen = self.update_players(current_time)

        if self.state == State.BROWSING or self.state == State.DIFF_SORTING:
            self.timer_browsing.update(current_time)
        elif self.state == State.SONG_SELECTED:
            self.timer_selected.update(current_time)

        if self.last_texture_index != self.texture_index:
            if not self.background_fade_change.is_started:
                self.background_fade_change.start()
            if self.background_fade_change.is_finished:
                self.last_texture_index = self.texture_index
                self.background_fade_change.reset()

        if self.game_transition is not None:
            self.game_transition.update(current_time)
            if self.game_transition.is_finished:
                return self.on_screen_end(next_screen)
        else:
            self.handle_input()

        if self.demo_song is not None:
            audio.update_music_stream(self.demo_song)

        if self.navigator.genre_bg is not None:
            self.navigator.genre_bg.update(current_time)

        if self.diff_sort_selector is not None:
            self.diff_sort_selector.update(current_time)

        self.check_for_selection()

        for song in self.navigator.items:
            song.box.update(current_time, self.state == State.SONG_SELECTED)
            if not song.box.text_loaded and (-156 * tex.screen_scale) <= song.box.position <= (tex.screen_width + 144) * tex.screen_scale:
                song.box.load_text()
            if not isinstance(song, Directory) and song.box.is_open:
                if self.demo_song is None and current_time >= song.box.wait + (83.33*3):
                    song.box.get_scores()
                    if song.tja.metadata.wave.exists() and song.tja.metadata.wave.is_file():
                        self.demo_song = audio.load_music_stream(song.tja.metadata.wave, 'demo_song')
                        audio.play_music_stream(self.demo_song, 'music')
                        audio.seek_music_stream(self.demo_song, song.tja.metadata.demostart)
                        audio.stop_sound('bgm')
                        logger.info(f"Demo song loaded and playing for {song.tja.metadata.title}")
            if song.box.is_open:
                current_box = song.box
                if not isinstance(current_box, BackBox) and current_time >= song.box.wait + (83.33*3):
                    self.texture_index = current_box.texture_index

        if ray.is_key_pressed(global_data.config["keys"]["back_key"]):
            logger.info("Back key pressed, returning to ENTRY screen")
            return self.on_screen_end('ENTRY')

    def draw_background_diffs(self):
        self.player_1.draw_background_diffs(self.state)

    def draw_players(self):
        self.player_1.draw(self.state)

    def draw(self):
        width = tex.textures['box']['background'].width
        for i in range(0, width * 4, width):
            tex.draw_texture('box', 'background', frame=self.last_texture_index, x=i-self.background_move.attribute)
            tex.draw_texture('box', 'background', frame=self.texture_index, x=i-self.background_move.attribute, fade=1 - self.background_fade_change.attribute)

        self.draw_background_diffs()

        if self.navigator.genre_bg is not None and self.state == State.BROWSING:
            self.navigator.genre_bg.draw(tex.skin_config["boxes"].y)

        self.navigator.draw_boxes(self.move_away.attribute, self.player_1.is_ura, self.diff_fade_out.attribute)

        if self.state == State.BROWSING:
            tex.draw_texture('global', 'arrow', index=0, x=-(self.blue_arrow_move.attribute*2), fade=self.blue_arrow_fade.attribute)
            tex.draw_texture('global', 'arrow', index=1, mirror='horizontal', x=self.blue_arrow_move.attribute*2, fade=self.blue_arrow_fade.attribute)
        tex.draw_texture('global', 'footer')

        self.ura_switch_animation.draw()

        if self.diff_sort_selector is not None:
            self.diff_sort_selector.draw()

        if (self.player_1.selected_song and self.state == State.SONG_SELECTED):
            tex.draw_texture('global', 'difficulty_select', fade=self.text_fade_in.attribute)
        elif self.state == State.DIFF_SORTING:
            tex.draw_texture('global', 'difficulty_select', fade=self.text_fade_in.attribute)
        else:
            tex.draw_texture('global', 'song_select', fade=self.text_fade_out.attribute)

        self.draw_players()

        if self.state == State.BROWSING and self.navigator.items != []:
            curr_item = self.navigator.get_current_item()
            if isinstance(curr_item, SongFile):
                curr_item.box.draw_score_history()

        self.indicator.draw(tex.skin_config['song_select_indicator'].x, tex.skin_config['song_select_indicator'].y)

        tex.draw_texture('global', 'song_num_bg', fade=0.75)
        tex.draw_texture('global', 'song_num', frame=global_data.songs_played % 4)
        if self.state == State.BROWSING or self.state == State.DIFF_SORTING:
            self.timer_browsing.draw()
        elif self.state == State.SONG_SELECTED:
            self.timer_selected.draw()
        self.coin_overlay.draw()
        if self.game_transition is not None:
            self.game_transition.draw()

        if self.dan_transition.is_started:
            self.dan_transition.draw()
        self.allnet_indicator.draw()

class SongSelectPlayer:
    def __init__(self, player_num: PlayerNum, text_fade_in):
        self.player_num = player_num
        self.selected_difficulty = -3
        self.prev_diff = -3
        self.selected_song = False
        self.is_ready = False
        self.is_ura = False
        self.ura_toggle = 0
        self.diff_select_move_right = False
        self.neiro_selector = None
        self.modifier_selector = None

        # References to shared animations
        self.diff_selector_move_1 = tex.get_animation(26, is_copy=True)
        self.diff_selector_move_2 = tex.get_animation(27, is_copy=True)
        self.text_fade_in = text_fade_in
        self.selected_diff_bounce = tex.get_animation(33, is_copy=True)
        self.selected_diff_fadein = tex.get_animation(34, is_copy=True)
        self.selected_diff_highlight_fade = tex.get_animation(35, is_copy=True)
        self.selected_diff_text_resize = tex.get_animation(36, is_copy=True)
        self.selected_diff_text_fadein = tex.get_animation(37, is_copy=True)

        # Player-specific objects
        self.chara = Chara2D(int(self.player_num) - 1)
        plate_info = global_data.config[f'nameplate_{self.player_num}p']
        self.nameplate = Nameplate(plate_info['name'], plate_info['title'],
            self.player_num, plate_info['dan'], plate_info['gold'], plate_info['rainbow'], plate_info['title_bg'])

    def update(self, current_time):
        """Update player state"""
        self.selected_diff_bounce.update(current_time)
        self.selected_diff_fadein.update(current_time)
        self.selected_diff_highlight_fade.update(current_time)
        self.selected_diff_text_resize.update(current_time)
        self.selected_diff_text_fadein.update(current_time)
        self.diff_selector_move_1.update(current_time)
        self.diff_selector_move_2.update(current_time)
        self.nameplate.update(current_time)
        self.chara.update(current_time, 100, False, False)

        if self.neiro_selector is not None:
            self.neiro_selector.update(current_time)
            if self.neiro_selector.is_finished:
                self.neiro_selector = None

        if self.modifier_selector is not None:
            self.modifier_selector.update(current_time)
            if self.modifier_selector.is_finished:
                self.modifier_selector = None

    def is_voice_playing(self):
        """Check if player voice is playing"""
        return audio.is_sound_playing(f'voice_start_song_{self.player_num}p')

    def on_song_selected(self, selected_song):
        """Called when a song is selected"""
        if Difficulty.URA not in selected_song.tja.metadata.course_data:
            self.is_ura = False
        elif (Difficulty.URA in selected_song.tja.metadata.course_data and
              Difficulty.ONI not in selected_song.tja.metadata.course_data):
            self.is_ura = True

    def handle_input_browsing(self, last_moved, selected_item):
        """Handle input for browsing songs. Returns action string or None."""
        current_time = get_current_ms()

        # Skip left (fast navigate)
        if ray.is_key_pressed(ray.KeyboardKey.KEY_LEFT_CONTROL) or (is_l_kat_pressed(self.player_num) and current_time <= last_moved + 50):
            audio.play_sound('skip', 'sound')
            return "skip_left"

        # Skip right (fast navigate)
        if ray.is_key_pressed(ray.KeyboardKey.KEY_RIGHT_CONTROL) or (is_r_kat_pressed(self.player_num) and current_time <= last_moved + 50):
            audio.play_sound('skip', 'sound')
            return "skip_right"

        # Navigate left
        if is_l_kat_pressed(self.player_num):
            audio.play_sound('kat', 'sound')
            return "navigate_left"

        # Navigate right
        if is_r_kat_pressed(self.player_num):
            audio.play_sound('kat', 'sound')
            return "navigate_right"

        # Select/Enter
        if is_l_don_pressed(self.player_num) or is_r_don_pressed(self.player_num):
            if selected_item is not None and isinstance(selected_item.box, BackBox):
                audio.play_sound('cancel', 'sound')
                return "go_back"
            elif isinstance(selected_item, Directory) and selected_item.collection == Directory.COLLECTIONS[3]:
                return "diff_sort"
            else:
                return "select_song"

        # Add favorite
        if ray.is_key_pressed(ray.KeyboardKey.KEY_SPACE):
            audio.play_sound('add_favorite', 'sound')
            return "add_favorite"

        return None

    def handle_input_diff_sort(self, diff_sort_selector):
        """Handle input for difficulty sorting. Returns (diff, level) tuple or None."""
        if is_l_kat_pressed(self.player_num):
            diff_sort_selector.input_left()
            audio.play_sound('kat', 'sound')

        if is_r_kat_pressed(self.player_num):
            diff_sort_selector.input_right()
            audio.play_sound('kat', 'sound')

        if is_l_don_pressed(self.player_num) or is_r_don_pressed(self.player_num):
            result = diff_sort_selector.input_select()
            audio.play_sound('don', 'sound')
            return result

        return None

    def handle_input(self, state, screen):
        """Main input dispatcher. Delegates to state-specific handlers."""
        if self.is_voice_playing() or self.is_ready:
            return

        if state == State.BROWSING:
            screen.handle_input_browsing()
        elif state == State.SONG_SELECTED:
            screen.handle_input_selected()
        elif state == State.DIFF_SORTING:
            screen.handle_input_diff_sort()

    def handle_input_selected(self, current_item):
        """Handle input for selecting difficulty. Returns 'cancel', 'confirm', or None"""
        if self.neiro_selector is not None:
            if is_l_kat_pressed(self.player_num):
                self.neiro_selector.move_left()
            elif is_r_kat_pressed(self.player_num):
                self.neiro_selector.move_right()
            if is_l_don_pressed(self.player_num) or is_r_don_pressed(self.player_num):
                audio.play_sound('don', 'sound')
                self.neiro_selector.confirm()
            return None

        if self.modifier_selector is not None:
            if is_l_kat_pressed(self.player_num):
                audio.play_sound('kat', 'sound')
                self.modifier_selector.left()
            elif is_r_kat_pressed(self.player_num):
                audio.play_sound('kat', 'sound')
                self.modifier_selector.right()
            if is_l_don_pressed(self.player_num) or is_r_don_pressed(self.player_num):
                audio.play_sound('don', 'sound')
                self.modifier_selector.confirm()
            return None

        if is_l_don_pressed(self.player_num) or is_r_don_pressed(self.player_num):
            if self.selected_difficulty == -3:
                return "cancel"
            elif self.selected_difficulty == -2:
                audio.play_sound('don', 'sound')
                self.modifier_selector = ModifierSelector(self.player_num)
                return None
            elif self.selected_difficulty == -1:
                audio.play_sound('don', 'sound')
                self.neiro_selector = NeiroSelector(self.player_num)
                return None
            else:
                self.is_ready = True
                return "confirm"

        if is_l_kat_pressed(self.player_num) or is_r_kat_pressed(self.player_num):
            audio.play_sound('kat', 'sound')
            selected_song = current_item
            if isinstance(selected_song, Directory):
                raise Exception("Directory was chosen instead of song")
            diffs = sorted(selected_song.tja.metadata.course_data)
            prev_diff = self.selected_difficulty
            ret_val = None

            if is_l_kat_pressed(self.player_num):
                ret_val = self._navigate_difficulty_left(diffs)
            elif is_r_kat_pressed(self.player_num):
                ret_val = self._navigate_difficulty_right(diffs)

            if Difficulty.EASY <= self.selected_difficulty <= Difficulty.URA and self.selected_difficulty != prev_diff:
                self.selected_diff_bounce.start()
                self.selected_diff_fadein.start()


            return ret_val

        if (ray.is_key_pressed(ray.KeyboardKey.KEY_TAB) and
            self.selected_difficulty in [Difficulty.ONI, Difficulty.URA]):
            return self._toggle_ura_mode()

        return None

    def _navigate_difficulty_left(self, diffs):
        """Navigate difficulty selection leftward"""
        self.diff_select_move_right = False
        if self.is_ura and self.selected_difficulty == Difficulty.URA:
            self.diff_selector_move_1.start()
            self.prev_diff = self.selected_difficulty
            if len(diffs) == 1:
                self.selected_difficulty = -1
            else:
                self.selected_difficulty = diffs[-3]
        elif self.selected_difficulty == -1 or self.selected_difficulty == -2:
            self.diff_selector_move_2.start()
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty -= 1
        elif self.selected_difficulty == -3:
            pass
        elif self.selected_difficulty not in diffs:
            self.prev_diff = self.selected_difficulty
            self.diff_selector_move_1.start()
            self.selected_difficulty = min(diffs)
        elif self.selected_difficulty == min(diffs):
            self.diff_selector_move_2.start()
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty = -1
        else:
            self.diff_selector_move_1.start()
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty = diffs[diffs.index(self.selected_difficulty) - 1]

    def _navigate_difficulty_right(self, diffs):
        """Navigate difficulty selection rightward"""
        self.diff_select_move_right = True
        if self.is_ura and self.selected_difficulty == Difficulty.HARD:
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty = Difficulty.URA
            self.diff_selector_move_1.start()

        if (self.selected_difficulty in [Difficulty.ONI, Difficulty.URA] and Difficulty.URA in diffs and Difficulty.ONI in diffs):
            self.ura_toggle = (self.ura_toggle + 1) % 10
            if self.ura_toggle == 0:
                return self._toggle_ura_mode()
        elif self.selected_difficulty == -1:
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty = min(diffs)
            self.diff_selector_move_2.start()
            self.diff_selector_move_1.start()
        elif self.selected_difficulty == -2 or self.selected_difficulty == -3:
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty += 1
            self.diff_selector_move_2.start()
        elif self.selected_difficulty < max(diffs):
            self.prev_diff = self.selected_difficulty
            self.selected_difficulty = diffs[diffs.index(self.selected_difficulty) + 1]
            self.diff_selector_move_1.start()

    def _toggle_ura_mode(self):
        """Toggle between ura and normal mode. Returns 'ura_toggle' to signal screen to play animation"""
        self.ura_toggle = 0
        self.is_ura = not self.is_ura
        audio.play_sound('ura_switch', 'sound')
        self.selected_difficulty = 7 - self.selected_difficulty
        return "ura_toggle"

    def draw_selector(self, is_half: bool):
        fade = 0.5 if (self.neiro_selector is not None or self.modifier_selector is not None) else self.text_fade_in.attribute
        direction = 1 if self.diff_select_move_right else -1
        offset = tex.skin_config["selector_offset"].x
        if self.selected_difficulty <= -1 or self.prev_diff == -1:
            if self.prev_diff == -1 and self.selected_difficulty >= 0:
                if not self.diff_selector_move_2.is_finished:
                    name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                    tex.draw_texture('diff_select', name, x=((self.prev_diff+3) * tex.skin_config["selector_balloon_offset_2"].x) + tex.skin_config["selector_balloon_offset_1"].x + (self.diff_selector_move_2.attribute * direction), fade=fade)
                    name = f'{self.player_num}p_outline_back_half' if is_half else f'{self.player_num}p_outline_back'
                    tex.draw_texture('diff_select', name, x=((self.prev_diff+3) * tex.skin_config["selector_balloon_offset_2"].x) + (self.diff_selector_move_2.attribute * direction))
                else:
                    difficulty = min(Difficulty.ONI, self.selected_difficulty)
                    name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                    tex.draw_texture('diff_select', name, x=(difficulty * offset), fade=fade)
                    name = f'{self.player_num}p_outline_half' if is_half else f'{self.player_num}p_outline'
                    tex.draw_texture('diff_select', name, x=(difficulty * offset))
            elif not self.diff_selector_move_2.is_finished:
                name = f'{self.player_num}p_outline_back_half' if is_half else f'{self.player_num}p_outline_back'
                tex.draw_texture('diff_select', name, x=((self.prev_diff+3) * tex.skin_config["selector_balloon_offset_2"].x) + (self.diff_selector_move_2.attribute * direction))
                if self.selected_difficulty != -3:
                    name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                    tex.draw_texture('diff_select', name, x=((self.prev_diff+3) * tex.skin_config["selector_balloon_offset_2"].x) + tex.skin_config["selector_balloon_offset_1"].x + (self.diff_selector_move_2.attribute * direction), fade=fade)
            else:
                name = f'{self.player_num}p_outline_back_half' if is_half else f'{self.player_num}p_outline_back'
                tex.draw_texture('diff_select', name, x=((self.selected_difficulty+3) * tex.skin_config["selector_balloon_offset_2"].x))
                if self.selected_difficulty != -3:
                    name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                    tex.draw_texture('diff_select', name, x=((self.selected_difficulty+3) * tex.skin_config["selector_balloon_offset_2"].x) + tex.skin_config["selector_balloon_offset_1"].x, fade=fade)
        else:
            if self.prev_diff == -1:
                return
            if not self.diff_selector_move_1.is_finished:
                difficulty = min(Difficulty.ONI, self.prev_diff)
                name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                tex.draw_texture('diff_select', name, x=(difficulty * offset) + (self.diff_selector_move_1.attribute * direction), fade=fade)
                name = f'{self.player_num}p_outline_half' if is_half else f'{self.player_num}p_outline'
                tex.draw_texture('diff_select', name, x=(difficulty * offset) + (self.diff_selector_move_1.attribute * direction))
            else:
                difficulty = min(Difficulty.ONI, self.selected_difficulty)
                name = f'{self.player_num}p_balloon_half' if is_half else f'{self.player_num}p_balloon'
                tex.draw_texture('diff_select', name, x=(difficulty * offset), fade=fade)
                name = f'{self.player_num}p_outline_half' if is_half else f'{self.player_num}p_outline'
                tex.draw_texture('diff_select', name, x=(difficulty * offset))

    def draw_background_diffs(self, state: int):
        if (self.selected_song and state == State.SONG_SELECTED and self.selected_difficulty >= Difficulty.EASY):
            if self.player_num == PlayerNum.P2:
                x_offset = 1025 * tex.screen_scale
                tex.draw_texture('global', 'background_diff', frame=self.selected_difficulty, fade=min(0.5, self.selected_diff_fadein.attribute), x=x_offset, y=-self.selected_diff_bounce.attribute, y2=self.selected_diff_bounce.attribute)
                if self.selected_diff_highlight_fade.is_reversing or self.selected_diff_highlight_fade.is_finished:
                    tex.draw_texture('global', 'background_diff', frame=self.selected_difficulty, x=x_offset, y=-self.selected_diff_bounce.attribute, y2=self.selected_diff_bounce.attribute)
                tex.draw_texture('global', 'background_diff_highlight', frame=min(Difficulty.ONI, self.selected_difficulty), fade=self.selected_diff_highlight_fade.attribute, x=x_offset)
                tex.draw_texture('global', 'bg_diff_text_bg', x=x_offset, fade=min(0.5, self.selected_diff_text_fadein.attribute), scale=self.selected_diff_text_resize.attribute, center=True)
                tex.draw_texture('global', 'bg_diff_text', frame=min(Difficulty.ONI, self.selected_difficulty), x=x_offset, fade=self.selected_diff_text_fadein.attribute, scale=self.selected_diff_text_resize.attribute, center=True)
            else:
                tex.draw_texture('global', 'background_diff', frame=self.selected_difficulty, fade=min(0.5, self.selected_diff_fadein.attribute), y=-self.selected_diff_bounce.attribute, y2=self.selected_diff_bounce.attribute)
                if self.selected_diff_highlight_fade.is_reversing or self.selected_diff_highlight_fade.is_finished:
                    tex.draw_texture('global', 'background_diff', frame=self.selected_difficulty, y=-self.selected_diff_bounce.attribute, y2=self.selected_diff_bounce.attribute)
                tex.draw_texture('global', 'background_diff_highlight', frame=min(Difficulty.ONI, self.selected_difficulty), fade=self.selected_diff_highlight_fade.attribute)
                tex.draw_texture('global', 'bg_diff_text_bg', fade=min(0.5, self.selected_diff_text_fadein.attribute), scale=self.selected_diff_text_resize.attribute, center=True)
                tex.draw_texture('global', 'bg_diff_text', frame=min(Difficulty.ONI, self.selected_difficulty), fade=self.selected_diff_text_fadein.attribute, scale=self.selected_diff_text_resize.attribute, center=True)

    def draw(self, state: int, is_half: bool = False):
        if (self.selected_song and state == State.SONG_SELECTED):
            self.draw_selector(is_half)

        offset = 0
        if self.neiro_selector is not None:
            offset = self.neiro_selector.move.attribute
            if self.neiro_selector.is_confirmed:
                offset += tex.skin_config["song_select_offset"].x
            else:
                offset *= -1
        if self.modifier_selector is not None:
            offset = self.modifier_selector.move.attribute
            if self.modifier_selector.is_confirmed:
                offset += tex.skin_config["song_select_offset"].x
            else:
                offset *= -1
        if self.player_num == PlayerNum.P1:
            self.nameplate.draw(tex.skin_config["song_select_nameplate_1p"].x, tex.skin_config["song_select_nameplate_1p"].y)
            self.chara.draw(x=tex.skin_config["song_select_chara_1p"].x, y=tex.skin_config["song_select_chara_1p"].y + (offset*0.6))
        else:
            self.nameplate.draw(tex.skin_config["song_select_nameplate_2p"].x, tex.skin_config["song_select_nameplate_2p"].y)
            self.chara.draw(mirror=True, x=tex.skin_config["song_select_chara_2p"].x, y=tex.skin_config["song_select_chara_2p"].y + (offset*0.6))

        if self.neiro_selector is not None:
            self.neiro_selector.draw()

        if self.modifier_selector is not None:
            self.modifier_selector.draw()

class UraSwitchAnimation:
    """The animation for the ura switch."""
    def __init__(self) -> None:
        self.texture_change = tex.get_animation(7)
        self.fade_out = tex.get_animation(8)
        self.fade_out.attribute = 0
    def start(self, is_backwards: bool):
        if is_backwards:
            self.texture_change = tex.get_animation(6)
        self.texture_change.start()
        self.fade_out.start()

    def update(self, current_ms: float):
        self.texture_change.update(current_ms)
        self.fade_out.update(current_ms)
    def draw(self):
        tex.draw_texture('diff_select', 'ura_switch', frame=self.texture_change.attribute, fade=self.fade_out.attribute)

class DiffSortSelect:
    """The menu for selecting the difficulty sort and level sort."""
    def __init__(self, statistics: dict[int, dict[int, list[int]]], prev_diff: int, prev_level: int):
        self.selected_box = -1
        self.selected_level = 1
        self.in_level_select = False
        self.confirmation = False
        self.confirm_index = 1
        self.num_boxes = 6
        self.limits = [5, 7, 8, 10]

        self.bg_resize = tex.get_animation(19)
        self.diff_fade_in = tex.get_animation(20)
        self.box_flicker = tex.get_animation(21)
        self.bounce_up_1 = tex.get_animation(22)
        self.bounce_down_1 = tex.get_animation(23)
        self.bounce_up_2 = tex.get_animation(24)
        self.bounce_down_2 = tex.get_animation(25)
        self.blue_arrow_fade = tex.get_animation(29)
        self.blue_arrow_move = tex.get_animation(30)
        self.blue_arrow_fade.start()
        self.blue_arrow_move.start()
        self.bg_resize.start()
        self.diff_fade_in.start()
        self.prev_diff = prev_diff
        self.prev_level = prev_level
        self.diff_sort_statistics = statistics
        self.diff_sort_sum_stat = {
            course: [
                sum(stats[0] for stats in levels.values()),
                sum(stats[1] for stats in levels.values()),
                sum(stats[2] for stats in levels.values())
            ]
            for course, levels in self.diff_sort_statistics.items()
        }
        audio.play_sound('voice_diff_sort_enter', 'voice')

    def update(self, current_ms):
        self.bg_resize.update(current_ms)
        self.diff_fade_in.update(current_ms)
        self.box_flicker.update(current_ms)
        self.bounce_up_1.update(current_ms)
        self.bounce_down_1.update(current_ms)
        self.bounce_up_2.update(current_ms)
        self.bounce_down_2.update(current_ms)

    def get_random_sort(self):
        diff = random.randint(0, 4)
        if diff == Difficulty.EASY:
            level = random.randint(1, 5)
        elif diff == Difficulty.NORMAL:
            level = random.randint(1, 7)
        elif diff == Difficulty.HARD:
            level = random.randint(1, 8)
        elif diff == Difficulty.ONI:
            level = random.randint(1, 10)
        else:
            level = random.choice([1, 5, 6, 7, 8, 9, 10])
        return diff, level

    def input_select(self):
        if self.confirmation:
            if self.confirm_index == 0:
                self.confirmation = False
                return None
            elif self.confirm_index == 1:
                return self.selected_box, self.selected_level
            elif self.confirm_index == 2:
                self.confirmation = False
                self.in_level_select = False
                return None
        elif self.in_level_select:
            self.confirmation = True
            self.bounce_up_1.start()
            self.bounce_down_1.start()
            self.bounce_up_2.start()
            self.bounce_down_2.start()
            self.confirm_index = 1
            audio.play_sound('voice_diff_sort_confirm', 'voice')
            return None
        if self.selected_box == -1:
            return (-1, -1)
        elif self.selected_box == 5:
            return (0, -1)
        elif self.selected_box == 4:
            return self.get_random_sort()
        audio.play_sound('voice_diff_sort_level', 'voice')
        self.in_level_select = True
        self.bg_resize.start()
        self.diff_fade_in.start()
        self.selected_level = min(self.selected_level, self.limits[self.selected_box])
        return None

    def input_left(self):
        if self.confirmation:
            self.confirm_index = max(self.confirm_index - 1, 0)
        elif self.in_level_select:
            self.selected_level = max(self.selected_level - 1, 1)
        else:
            self.selected_box = max(self.selected_box - 1, -1)

    def input_right(self):
        if self.confirmation:
            self.confirm_index = min(self.confirm_index + 1, 2)
        elif self.in_level_select:
            self.selected_level = min(self.selected_level + 1, self.limits[self.selected_box])
        else:
            self.selected_box = min(self.selected_box + 1, self.num_boxes - 1)

    def draw_statistics(self):
        tex.draw_texture('diff_sort', f'stat_bg_{global_data.player_num}p')
        tex.draw_texture('diff_sort', 'stat_overlay')
        tex.draw_texture('diff_sort', 'stat_diff', frame=min(self.selected_box, 3))
        if self.in_level_select or self.selected_box == 5:
            tex.draw_texture('diff_sort', 'stat_starx')
            if self.selected_box == 5:
                tex.draw_texture('diff_sort', 'stat_prev')
                counter = str(self.prev_level)
            else:
                counter = str(self.selected_level)
            margin = tex.skin_config["diff_sort_margin_1"].x
            total_width = len(counter) * margin
            for i, digit in enumerate(counter):
                tex.draw_texture('diff_sort', 'stat_num_star', frame=int(digit), x=tex.skin_config["diff_sort_stat_num_star"].y-(len(counter) - i) * margin, y=tex.skin_config["diff_sort_stat_num_star"].y)
            counter = str(self.diff_sort_statistics[self.selected_box][self.selected_level][0])
            if self.selected_box == 5:
                counter = str(self.diff_sort_statistics[self.prev_diff][self.prev_level][0])
            margin = tex.skin_config["diff_sort_margin_2"].x
            total_width = len(counter) * margin
            for i, digit in enumerate(counter):
                tex.draw_texture('diff_sort', 'stat_num', frame=int(digit), x=-(total_width//2)+(i*margin))

            for j in range(2):
                if self.selected_box == 5:
                    counter = str(self.diff_sort_statistics[self.prev_diff][self.prev_level][0])
                else:
                    counter = str(self.diff_sort_statistics[self.selected_box][self.selected_level][0])
                margin = tex.skin_config["diff_sort_margin_3"].x
                total_width = len(counter) * margin
                for i, digit in enumerate(counter):
                    tex.draw_texture('diff_sort', 'stat_num_small', index=j, frame=int(digit), x=-(total_width//2)+(i*margin))

            for j in range(2):
                if self.selected_box == 5:
                    counter = str(self.diff_sort_statistics[self.prev_diff][self.prev_level][j+1])
                else:
                    counter = str(self.diff_sort_statistics[self.selected_box][self.selected_level][j+1])
                margin = tex.skin_config["diff_sort_margin_1"].x
                total_width = len(counter) * margin
                for i, digit in enumerate(counter):
                    tex.draw_texture('diff_sort', 'stat_num_star', index=j, frame=int(digit), x=-(len(counter) - i) * margin)
        else:
            counter = str(self.diff_sort_sum_stat[self.selected_box][0])
            margin = tex.skin_config["diff_sort_margin_2"].x
            total_width = len(counter) * margin
            for i, digit in enumerate(counter):
                tex.draw_texture('diff_sort', 'stat_num', frame=int(digit), x=-(total_width//2)+(i*margin))

            for j in range(2):
                counter = str(self.diff_sort_sum_stat[self.selected_box][0])
                margin = tex.skin_config["diff_sort_margin_3"].x
                total_width = len(counter) * margin
                for i, digit in enumerate(counter):
                    tex.draw_texture('diff_sort', 'stat_num_small', index=j, frame=int(digit), x=-(total_width//2)+(i*margin))

            for j in range(2):
                counter = str(self.diff_sort_sum_stat[self.selected_box][j+1])
                margin = tex.skin_config["diff_sort_margin_1"].x
                total_width = len(counter) * margin
                for i, digit in enumerate(counter):
                    tex.draw_texture('diff_sort', 'stat_num_star', index=j, frame=int(digit), x=-(len(counter) - i) * margin)

    def draw_diff_select(self):
        tex.draw_texture('diff_sort', 'background', scale=self.bg_resize.attribute, center=True)

        tex.draw_texture('diff_sort', 'back', fade=self.diff_fade_in.attribute)
        offset = tex.skin_config["diff_sort_offset"].x
        for i in range(self.num_boxes):
            if i == self.selected_box:
                tex.draw_texture('diff_sort', 'box_highlight', x=(offset*i), fade=self.diff_fade_in.attribute)
                tex.draw_texture('diff_sort', 'box_text_highlight', x=(offset*i), frame=i, fade=self.diff_fade_in.attribute)
            else:
                tex.draw_texture('diff_sort', 'box', x=(offset*i), fade=self.diff_fade_in.attribute)
                tex.draw_texture('diff_sort', 'box_text', x=(offset*i), frame=i, fade=self.diff_fade_in.attribute)
        if self.selected_box == -1:
            tex.draw_texture('diff_sort', 'back_outline', fade=self.box_flicker.attribute)
        else:
            tex.draw_texture('diff_sort', 'box_outline', x=(offset*self.selected_box), fade=self.box_flicker.attribute)

        for i in range(self.num_boxes):
            if i < 4:
                tex.draw_texture('diff_sort', 'box_diff', x=(offset*i), frame=i)

        if Difficulty.EASY <= self.selected_box <= Difficulty.ONI or self.selected_box == 5:
            self.draw_statistics()

    def draw_level_select(self):
        tex.draw_texture('diff_sort', 'background', scale=self.bg_resize.attribute, center=True)
        if self.confirmation:
            tex.draw_texture('diff_sort', 'star_select_prompt')
        else:
            tex.draw_texture('diff_sort', 'star_select_text', fade=self.diff_fade_in.attribute)
        tex.draw_texture('diff_sort', 'star_limit', frame=self.selected_box, fade=self.diff_fade_in.attribute)
        tex.draw_texture('diff_sort', 'level_box', fade=self.diff_fade_in.attribute)
        tex.draw_texture('diff_sort', 'diff', frame=self.selected_box, fade=self.diff_fade_in.attribute)
        tex.draw_texture('diff_sort', 'star_num', frame=self.selected_level, fade=self.diff_fade_in.attribute)
        for i in range(self.selected_level):
            tex.draw_texture('diff_sort', 'star', x=(i*(40.5 * tex.screen_scale)), fade=self.diff_fade_in.attribute)

        if self.confirmation:
            texture = tex.textures['diff_sort']['level_box']
            ray.draw_rectangle(int(texture.x[0]), int(texture.y[0]), int(texture.x2[0]), int(texture.y2[0]), ray.fade(ray.BLACK, 0.5))
            y = -self.bounce_up_1.attribute + self.bounce_down_1.attribute - self.bounce_up_2.attribute + self.bounce_down_2.attribute
            offset = tex.skin_config['diff_sort_offset_2'].x
            for i in range(3):
                if i == self.confirm_index:
                    tex.draw_texture('diff_sort', 'small_box_highlight', x=(i*offset), y=y)
                    tex.draw_texture('diff_sort', 'small_box_text_highlight', x=(i*offset), y=y, frame=i)
                    tex.draw_texture('diff_sort', 'small_box_outline', x=(i*offset), y=y, fade=self.box_flicker.attribute)
                else:
                    tex.draw_texture('diff_sort', 'small_box', x=(i*offset), y=y)
                    tex.draw_texture('diff_sort', 'small_box_text', x=(i*offset), y=y, frame=i)
        else:
            tex.draw_texture('diff_sort', 'pongos')
            if self.selected_level != 1:
                tex.draw_texture('diff_sort', 'arrow', index=0, x=-self.blue_arrow_move.attribute, fade=self.blue_arrow_fade.attribute)
            if self.selected_level != self.limits[self.selected_box]:
                tex.draw_texture('diff_sort', 'arrow', index=1, mirror='horizontal', x=self.blue_arrow_move.attribute, fade=self.blue_arrow_fade.attribute)
        self.draw_statistics()

    def draw(self):
        ray.draw_rectangle(0, 0, tex.screen_width, tex.screen_height, ray.fade(ray.BLACK, 0.6))
        if self.in_level_select:
            self.draw_level_select()
        else:
            self.draw_diff_select()

class NeiroSelector:
    """The menu for selecting the game hitsounds."""
    def __init__(self, player_num: PlayerNum):
        self.player_num = player_num
        self.selected_sound = global_data.hit_sound[self.player_num]
        with open(Path("Sounds") / 'hit_sounds' / 'neiro_list.txt', encoding='utf-8-sig') as neiro_list:
            self.sounds = neiro_list.readlines()
            self.sounds.append('無音')
        self.load_sound()
        audio.play_sound(f'voice_hitsound_select_{self.player_num}p', 'voice')
        self.is_finished = False
        self.is_confirmed = False
        self.move = tex.get_animation(28, is_copy=True)
        self.move.start()
        self.blue_arrow_fade = tex.get_animation(29, is_copy=True)
        self.blue_arrow_move = tex.get_animation(30, is_copy=True)
        self.text = OutlinedText(self.sounds[self.selected_sound], tex.skin_config["neiro_text"].font_size, ray.WHITE)
        self.text_2 = OutlinedText(self.sounds[self.selected_sound], tex.skin_config["neiro_text"].font_size, ray.WHITE)
        self.move_sideways = tex.get_animation(31, is_copy=True)
        self.fade_sideways = tex.get_animation(32, is_copy=True)
        self.direction = -1

    def load_sound(self):
        if self.selected_sound == len(self.sounds):
            return
        if self.selected_sound == 0:
            self.curr_sound = audio.load_sound(Path("Sounds") / "hit_sounds" / str(self.selected_sound) / "don.wav", 'hit_sound')
        else:
            self.curr_sound = audio.load_sound(Path("Sounds") / "hit_sounds" / str(self.selected_sound) / "don.ogg", 'hit_sound')

    def move_left(self):
        if self.move.is_started and not self.move.is_finished:
            return
        self.selected_sound = (self.selected_sound - 1) % len(self.sounds)
        audio.unload_sound(self.curr_sound)
        self.load_sound()
        self.move_sideways.start()
        self.fade_sideways.start()

        self.text.unload()
        self.text = self.text_2
        self.text_2 = OutlinedText(self.sounds[self.selected_sound], tex.skin_config["neiro_text"].font_size, ray.WHITE)

        self.direction = -1
        if self.selected_sound == len(self.sounds):
            return
        audio.play_sound(self.curr_sound, 'hitsound')

    def move_right(self):
        if self.move.is_started and not self.move.is_finished:
            return
        self.selected_sound = (self.selected_sound + 1) % len(self.sounds)
        audio.unload_sound(self.curr_sound)
        self.load_sound()
        self.move_sideways.start()
        self.fade_sideways.start()

        self.text.unload()
        self.text = self.text_2
        self.text_2 = OutlinedText(self.sounds[self.selected_sound], tex.skin_config["neiro_text"].font_size, ray.WHITE)

        self.direction = 1
        if self.selected_sound == len(self.sounds):
            return
        audio.play_sound(self.curr_sound, 'hitsound')

    def confirm(self):
        if self.move.is_started and not self.move.is_finished:
            return
        if self.selected_sound == len(self.sounds):
            global_data.hit_sound[self.player_num] = -1
        else:
            global_data.hit_sound[self.player_num] = self.selected_sound
        self.is_confirmed = True
        self.move.restart()

    def update(self, current_ms):
        self.move.update(current_ms)
        self.blue_arrow_fade.update(current_ms)
        self.blue_arrow_move.update(current_ms)
        self.move_sideways.update(current_ms)
        self.fade_sideways.update(current_ms)
        self.is_finished = self.move.is_finished and self.is_confirmed

    def draw(self):
        if self.is_confirmed:
            y = tex.skin_config["song_select_offset"].x + self.move.attribute
        else:
            y = -self.move.attribute
        x = (int(self.player_num) - 1) * tex.skin_config["option_p2"].x
        tex.draw_texture('neiro', 'background', x=x, y=y)
        tex.draw_texture('neiro', f'{self.player_num}p', x=x, y=y)
        tex.draw_texture('neiro', 'divisor', x=x, y=y)
        tex.draw_texture('neiro', 'music_note', y=y, x=x+(self.move_sideways.attribute*self.direction), fade=self.fade_sideways.attribute)
        tex.draw_texture('neiro', 'music_note', y=y, x=x+(self.direction*-tex.skin_config["option_text_in"].x) + (self.move_sideways.attribute*self.direction), fade=1 - self.fade_sideways.attribute)
        tex.draw_texture('neiro', 'blue_arrow', y=y, x=x-self.blue_arrow_move.attribute, fade=self.blue_arrow_fade.attribute)
        tex.draw_texture('neiro', 'blue_arrow', y=y, x=x+(tex.skin_config["option_text_in"].x*2) + self.blue_arrow_move.attribute, mirror='horizontal', fade=self.blue_arrow_fade.attribute)

        counter = str(self.selected_sound+1)
        total_width = len(counter) * tex.skin_config["neiro_counter_margin"].x
        for i in range(len(counter)):
            tex.draw_texture('neiro', 'counter', frame=int(counter[i]), x=x-(total_width // 2) + (i * tex.skin_config["neiro_counter_margin"].x), y=y)

        counter = str(len(self.sounds))
        total_width = len(counter) * tex.skin_config["neiro_counter_margin"].x
        for i in range(len(counter)):
            tex.draw_texture('neiro', 'counter', frame=int(counter[i]), x=x-(total_width // 2) + (i * tex.skin_config["neiro_counter_margin"].x) + (60 * tex.screen_scale), y=y)

        self.text.draw(outline_color=ray.BLACK, x=x+tex.skin_config["neiro_text"].x - (self.text.texture.width//2) + (self.move_sideways.attribute*self.direction), y=y+tex.skin_config["neiro_text"].y, color=ray.fade(ray.WHITE, self.fade_sideways.attribute))
        self.text_2.draw(outline_color=ray.BLACK, x=x+(self.direction*-tex.skin_config["option_text_in"].x) + tex.skin_config["neiro_text"].x - (self.text_2.texture.width//2) + (self.move_sideways.attribute*self.direction), y=y+tex.skin_config["neiro_text"].y, color=ray.fade(ray.WHITE, 1 - self.fade_sideways.attribute))

class ModifierSelector:
    """The menu for selecting the game modifiers."""
    TEX_MAP = {
        "auto": "mod_auto",
        "speed": "mod_baisaku",
        "display": "mod_doron",
        "inverse": "mod_abekobe",
        "random": "mod_kimagure"
    }
    NAME_MAP = {
        "auto": "オート",
        "speed": "はやさ",
        "display": "ドロン",
        "inverse": "あべこべ",
        "random": "ランダム"
    }
    def __init__(self, player_num: PlayerNum):
        self.player_num = player_num
        self.mods = fields(Modifiers)
        self.current_mod_index = 0
        self.is_confirmed = False
        self.is_finished = False
        self.blue_arrow_fade = tex.get_animation(29, is_copy=True)
        self.blue_arrow_move = tex.get_animation(30, is_copy=True)
        self.move = tex.get_animation(28, is_copy=True)
        self.move.start()
        self.move_sideways = tex.get_animation(31, is_copy=True)
        self.fade_sideways = tex.get_animation(32, is_copy=True)
        self.direction = -1
        audio.play_sound(f'voice_options_{self.player_num}p', 'sound')
        self.text_name = [OutlinedText(ModifierSelector.NAME_MAP[mod.name], tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5) for mod in self.mods]
        self.text_true = OutlinedText('する', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_false = OutlinedText('しない', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_speed = OutlinedText(str(global_data.modifiers[self.player_num].speed), tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_kimagure = OutlinedText('きまぐれ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_detarame = OutlinedText('でたらめ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)

        # Secondary text objects for animation
        self.text_true_2 = OutlinedText('する', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_false_2 = OutlinedText('しない', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_speed_2 = OutlinedText(str(global_data.modifiers[self.player_num].speed), tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_kimagure_2 = OutlinedText('きまぐれ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        self.text_detarame_2 = OutlinedText('でたらめ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)

    def update(self, current_ms):
        self.is_finished = self.is_confirmed and self.move.is_finished
        if self.is_finished:
            for text in self.text_name:
                text.unload()
        self.move.update(current_ms)
        self.blue_arrow_fade.update(current_ms)
        self.blue_arrow_move.update(current_ms)
        self.move_sideways.update(current_ms)
        self.fade_sideways.update(current_ms)
        # Removed conditional update - now handled immediately in left/right methods

    def confirm(self):
        if self.is_confirmed:
            return
        self.current_mod_index += 1
        if self.current_mod_index == len(self.mods):
            self.is_confirmed = True
            self.move.restart()

    def _start_text_animation(self, direction, old_value):
        self.move_sideways.start()
        self.fade_sideways.start()
        self.direction = direction

        # Update primary text objects immediately
        current_mod = self.mods[self.current_mod_index]
        current_value = getattr(global_data.modifiers[self.player_num], current_mod.name)

        if current_mod.name == 'speed':
            # text_speed_2 becomes the old value (fades out)
            # text_speed becomes the new value (fades in)
            self.text_speed_2.unload()
            self.text_speed_2 = self.text_speed
            self.text_speed = OutlinedText(str(current_value), tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        elif current_mod.type is bool:
            if current_value:
                self.text_true.unload()
                self.text_true = self.text_true_2
                self.text_true_2 = OutlinedText('する', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
            else:
                self.text_false.unload()
                self.text_false = self.text_false_2
                self.text_false_2 = OutlinedText('しない', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
        elif current_mod.name == 'random':
            if current_value == 1:
                self.text_kimagure.unload()
                self.text_kimagure = self.text_kimagure_2
                self.text_kimagure_2 = OutlinedText('きまぐれ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)
            elif current_value == 2:
                self.text_detarame.unload()
                self.text_detarame = self.text_detarame_2
                self.text_detarame_2 = OutlinedText('でたらめ', tex.skin_config["modifier_text"].font_size, ray.WHITE, outline_thickness=3.5)

    def left(self):
        if self.is_confirmed:
            return
        current_mod = self.mods[self.current_mod_index]
        current_value = getattr(global_data.modifiers[self.player_num], current_mod.name)
        if current_mod.type is bool:
            setattr(global_data.modifiers[self.player_num], current_mod.name, not current_value)
            self._start_text_animation(-1, current_value)
        elif current_mod.name == 'speed':
            new_value = max(1, (current_value*10 - 1))/10
            setattr(global_data.modifiers[self.player_num], current_mod.name, new_value)
            self._start_text_animation(-1, current_value)
        elif current_mod.name == 'random':
            new_value = max(0, current_value-1)
            setattr(global_data.modifiers[self.player_num], current_mod.name, new_value)
            self._start_text_animation(-1, current_value)

    def right(self):
        if self.is_confirmed:
            return
        current_mod = self.mods[self.current_mod_index]
        current_value = getattr(global_data.modifiers[self.player_num], current_mod.name)
        if current_mod.type is bool:
            setattr(global_data.modifiers[self.player_num], current_mod.name, not current_value)
            self._start_text_animation(1, current_value)
        elif current_mod.name == 'speed':
            new_value = (current_value*10 + 1)/10
            setattr(global_data.modifiers[self.player_num], current_mod.name, new_value)
            self._start_text_animation(1, current_value)
        elif current_mod.name == 'random':
            new_value = (current_value+1) % 3
            setattr(global_data.modifiers[self.player_num], current_mod.name, new_value)
            self._start_text_animation(1, current_value)

    def _draw_animated_text(self, text_primary: OutlinedText, text_secondary: OutlinedText, x: float, y: float, should_animate: bool):
        if should_animate and not self.move_sideways.is_finished:
            # Draw primary text moving out
            text_primary.draw(outline_color=ray.BLACK, x=x + (self.move_sideways.attribute * self.direction), y=y, color=ray.fade(ray.WHITE, self.fade_sideways.attribute))

            # Draw secondary text moving in
            text_secondary.draw(outline_color=ray.BLACK, x=(self.direction * -tex.skin_config["option_text_in"].x) + x + (self.move_sideways.attribute * self.direction), y=y, color=ray.fade(ray.WHITE, 1 - self.fade_sideways.attribute))
        else:
            # Draw static text
            text_primary.draw(outline_color=ray.BLACK, x=x, y=y)

    def draw(self):
        if self.is_confirmed:
            move = self.move.attribute - tex.skin_config["song_select_offset"].x
        else:
            move = -self.move.attribute
        x = (int(self.player_num) - 1) * tex.skin_config["option_p2"].x
        tex.draw_texture('modifier', 'top', y=move, x=x)
        tex.draw_texture('modifier', f'{self.player_num}p', y=move, x=x)
        tex.draw_texture('modifier', 'bottom', y=move + (len(self.mods)*tex.skin_config["modifier_offset"].y), x=x)

        for i in range(len(self.mods)):
            tex.draw_texture('modifier', 'background', y=move + (i*tex.skin_config["modifier_offset"].y), x=x)
            if i == self.current_mod_index:
                tex.draw_texture('modifier', 'mod_bg_highlight', y=move + (i*tex.skin_config["modifier_offset"].y), x=x)
            else:
                tex.draw_texture('modifier', 'mod_bg', y=move + (i*tex.skin_config["modifier_offset"].y), x=x)
            tex.draw_texture('modifier', 'mod_box', y=move + (i*tex.skin_config["modifier_offset"].y), x=x)
            self.text_name[i].draw(outline_color=ray.BLACK, x=tex.skin_config["modifier_offset_2"].x + x, y=tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y))

            current_mod = self.mods[i]
            current_value = getattr(global_data.modifiers[self.player_num], current_mod.name)
            is_current_mod = (i == self.current_mod_index)

            if current_mod.type is bool:
                if current_value:
                    tex.draw_texture('modifier', ModifierSelector.TEX_MAP[self.mods[i].name], y=move + (i*tex.skin_config["modifier_offset"].y), x=x)
                    text_x = tex.skin_config["modifier_text"].x - (self.text_true.texture.width//2)
                    text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                    self._draw_animated_text(self.text_true, self.text_true_2, text_x + x, text_y, is_current_mod)
                else:
                    text_x = tex.skin_config["modifier_text"].x - (self.text_false.texture.width//2)
                    text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                    self._draw_animated_text(self.text_false, self.text_false_2, text_x + x, text_y, is_current_mod)
            elif current_mod.name == 'speed':
                text_x = tex.skin_config["modifier_text"].x - (self.text_speed.texture.width//2)
                text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                self._draw_animated_text(self.text_speed, self.text_speed_2, text_x + x, text_y, is_current_mod)

                if current_value >= 4.0:
                    tex.draw_texture('modifier', 'mod_yonbai', x=x, y=move + (i*tex.skin_config["modifier_offset"].y))
                elif current_value >= 3.0:
                    tex.draw_texture('modifier', 'mod_sanbai', x=x, y=move + (i*tex.skin_config["modifier_offset"].y))
                elif current_value > 1.0:
                    tex.draw_texture('modifier', ModifierSelector.TEX_MAP[self.mods[i].name], x=x, y=move + (i*tex.skin_config["modifier_offset"].y))
            elif current_mod.name == 'random':
                if current_value == 1:
                    text_x = tex.skin_config["modifier_text"].x - (self.text_kimagure.texture.width//2)
                    text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                    self._draw_animated_text(self.text_kimagure, self.text_kimagure_2, text_x + x, text_y, is_current_mod)
                    tex.draw_texture('modifier', ModifierSelector.TEX_MAP[self.mods[i].name], x=x, y=move + (i*tex.skin_config["modifier_offset"].y))
                elif current_value == 2:
                    text_x = tex.skin_config["modifier_text"].x - (self.text_detarame.texture.width//2)
                    text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                    self._draw_animated_text(self.text_detarame, self.text_detarame_2, text_x + x, text_y, is_current_mod)
                    tex.draw_texture('modifier', 'mod_detarame', x=x, y=move + (i*tex.skin_config["modifier_offset"].y))
                else:
                    text_x = tex.skin_config["modifier_text"].x - (self.text_false.texture.width//2)
                    text_y = tex.skin_config["modifier_text"].y + move + (i*tex.skin_config["modifier_offset"].y)
                    self._draw_animated_text(self.text_false, self.text_false_2, text_x + x, text_y, is_current_mod)

            if i == self.current_mod_index:
                tex.draw_texture('modifier', 'blue_arrow', y=move + (i*tex.skin_config["modifier_offset"].y), x=x-self.blue_arrow_move.attribute, fade=self.blue_arrow_fade.attribute)
                tex.draw_texture('modifier', 'blue_arrow', y=move + (i*tex.skin_config["modifier_offset"].y), x=x+tex.skin_config["modifier_offset_2"].y + self.blue_arrow_move.attribute, mirror='horizontal', fade=self.blue_arrow_fade.attribute)

class DanTransition:
    def __init__(self):
        self.slide_in = tex.get_animation(38)
        self.is_finished = False
        self.is_started = False

    def start(self):
        self.slide_in.start()
        self.is_started = True

    def update(self, current_time_ms: float):
        self.slide_in.update(current_time_ms)
        if self.slide_in.is_finished:
            self.is_finished = True

    def draw(self):
        tex.draw_texture('dan_transition', 'background', x2=self.slide_in.attribute)
