import pyray as ray
import numpy as np
import vlc
import cv2
from global_funcs import Animation, VideoPlayer, get_current_ms

class TitleScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.op_video = VideoPlayer('Videos\\OP.mp4')
        self.warning = None
        self.load_textures()

    def load_textures(self):
        self.texture_bg = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00000.png')
        self.texture_warning = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00001.png')
        self.texture_warning_ch1 = [ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00004.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00009.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00016.png')]
        self.texture_warning_ch1_base = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00002.png')
        self.texture_warning_ch2 = [ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00005.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00006.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00007.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00008.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00010.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00011.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00012.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00013.png'),
                                    ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00017.png')]
        self.texture_warning_ch2_base = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00003.png')
        self.texture_warning_bachi = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00019.png')
        self.texture_warning_bachi_hit = ray.load_texture('Graphics\\lumendata\\attract\\keikoku\\keikoku_img00018.png')

        self.sound_bachi_swipe = ray.load_sound('Sounds\\title\\SE_ATTRACT_2.ogg')
        self.sound_bachi_hit = ray.load_sound('Sounds\\title\\SE_ATTRACT_3.ogg')

    def animation_manager(self):
        if self.warning is not None:
            self.warning.update(get_current_ms(), self)

    def update(self):
        self.animation_manager()
        if self.op_video is not None:
            self.op_video.update()
            if all(self.op_video.is_finished):
                self.op_video = None
                self.warning = WarningBoard(get_current_ms(), self)
        if ray.is_key_pressed(ray.KeyboardKey.KEY_ENTER):
            return "ENTRY"
        return None

    def draw_animation(self):
        if self.warning is not None:
            self.warning.draw(self)
    def draw(self):
        if self.op_video is not None:
            self.op_video.draw()
            return
        bg_source = ray.Rectangle(0, 0, self.texture_bg.width, self.texture_bg.height)
        bg_dest = ray.Rectangle(0, 0, self.width, self.height)
        ray.draw_texture_pro(self.texture_bg, bg_source, bg_dest, ray.Vector2(0,0), 0, ray.WHITE)
        self.draw_animation()

class WarningBoard:
    def __init__(self, current_ms, title_screen):
        self.start_ms = current_ms
        self.move_animation_1 = Animation(current_ms, 266.67, 'move')
        self.move_animation_1.params['start_position'] = -720
        self.move_animation_1.params['total_distance'] = title_screen.height + ((title_screen.height - title_screen.texture_warning.height)//2) + 20

        self.move_animation_2 = Animation(current_ms, 116.67, 'move')
        self.move_animation_2.params['start_position'] = 92 + 20
        self.move_animation_2.params['delay'] = 266.67
        self.move_animation_2.params['total_distance'] = -30

        self.move_animation_3 = Animation(current_ms, 116.67, 'move')
        self.move_animation_3.params['start_position'] = 82
        self.move_animation_3.params['delay'] = 383.34
        self.move_animation_3.params['total_distance'] = 10

        self.fade_animation_1 = Animation(current_ms, 300, 'fade')
        self.fade_animation_1.params['delay'] = 266.67
        self.fade_animation_1.params['initial_opacity'] = 0.0
        self.fade_animation_1.params['final_opacity'] = 1.0
        self.character_time = 0
        self.character_index_val = 0
        self.hit_played = False

    def update(self, current_ms, title_screen):
        self.move_animation_1.update(current_ms)
        self.move_animation_2.update(current_ms)
        self.move_animation_3.update(current_ms)
        self.fade_animation_1.update(current_ms)
        delay = 566.67
        if delay <= current_ms - self.start_ms and self.character_index(1) != 8:
            if not ray.is_sound_playing(title_screen.sound_bachi_swipe):
                ray.play_sound(title_screen.sound_bachi_swipe)
        elif self.character_index(1) == 8 and not self.hit_played:
            self.hit_played = True
            ray.play_sound(title_screen.sound_bachi_hit)

    def character_index(self, index):
        elapsed_time = get_current_ms() - self.start_ms
        delay = 566.67
        animation = [(300.00, 1, 0), (183.33, 2, 0), (166.67, 3, 0), (166.67, 4, 1), (166.67, 5, 1), (166.67, 6, 1), (166.67, 7, 1),
                     (166.67, 0, 0), (150.00, 1, 0), (133.34, 2, 0), (133.34, 3, 0), (133.34, 4, 1), (133.34, 5, 1), (133.34, 6, 1), (133.34, 7, 1),
                     (133.34, 0, 0), (116.67, 1, 0), (100.00, 2, 0), (100.00, 3, 0), (100.00, 4, 1), (100.00, 5, 1), (100.00, 6, 1), (100.00, 7, 1),
                     (100.00, 0, 0), (100.00, 1, 0), (83.330, 2, 0), (83.330, 3, 0), (83.330, 4, 1), (83.330, 5, 1), (83.330, 6, 1), (83.330, 7, 1),
                     (83.330, 0, 0), (83.330, 1, 0), (66.670, 2, 0), (66.670, 3, 0), (66.670, 4, 1), (66.670, 5, 1), (66.670, 6, 1), (66.670, 7, 1),
                     (66.670, 0, 0), (66.670, 1, 0), (66.670, 2, 0), (66.670, 3, 0), (66.670, 4, 1), (66.670, 5, 1), (66.670, 6, 1), (66.670, 7, 1),
                     (66.670, 0, 0), (66.670, 1, 0), (66.670, 2, 0), (66.670, 3, 0), (66.670, 4, 1), (66.670, 5, 1), (66.670, 6, 1), (66.670, 7, 1),
                     (66.670, 8, 2)]
        if self.character_index_val == len(animation)-1:
            return animation[len(animation)-1][index]
        elif elapsed_time <= delay:
            return 0
        elif elapsed_time >= delay + self.character_time:
            new_index = animation[self.character_index_val][index]
            self.character_index_val += 1
            self.character_time += animation[self.character_index_val][0]
            return new_index
        else:
            return animation[self.character_index_val][index]

    def draw(self, title_screen):
        if self.move_animation_2.is_finished:
            y = self.move_animation_3.attribute
        elif self.move_animation_1.is_finished:
            y = self.move_animation_2.attribute
        else:
            y = self.move_animation_1.attribute
        ray.draw_texture(title_screen.texture_warning, 0, int(y), ray.WHITE)
        fade = ray.fade(ray.WHITE, self.fade_animation_1.attribute)
        fade_2 = ray.fade(ray.WHITE, self.fade_animation_1.attribute if self.fade_animation_1.attribute < 0.75 else 0.75)
        ray.draw_texture(title_screen.texture_warning_ch1_base, 135, int(y)+title_screen.texture_warning_ch1[0].height+110, fade_2)
        ray.draw_texture(title_screen.texture_warning_ch1[self.character_index(2)], 115, int(y)+150, fade)
        ray.draw_texture(title_screen.texture_warning_ch2_base, 360, int(y)+title_screen.texture_warning_ch2[0].height+60, fade_2)
        ray.draw_texture(title_screen.texture_warning_ch2[self.character_index(1)], 315, int(y)+100, fade)
        if self.character_index(1) == 8:
            ray.draw_texture(title_screen.texture_warning_bachi, 350, int(y)+135, ray.WHITE)
