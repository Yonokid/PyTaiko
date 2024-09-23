import pyray as ray
import numpy as np
import cv2
import os
import random
from global_funcs import Animation, VideoPlayer, get_current_ms, load_texture_from_zip

class TitleScreen:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.op_videos = []
        for root, folder, files in os.walk('Videos\\op_videos'):
            for file in files:
                if file.endswith('.mp4'):
                    self.op_videos.append(VideoPlayer(root + '\\' + file))
        self.current_op_video = random.choice(self.op_videos)
        self.attract_videos = []
        for root, folder, files in os.walk('Videos\\attract_videos'):
            for file in files:
                if file.endswith('.mp4'):
                    self.attract_videos.append(VideoPlayer(root + '\\' + file))
        self.current_attract_video = None
        self.warning = None
        self.scene = None
        self.load_textures()

    def load_textures(self):
        zip_file = 'Graphics\\lumendata\\attract\\keikoku.zip'
        self.texture_bg = load_texture_from_zip(zip_file, 'keikoku_img00000.png')
        self.texture_warning = load_texture_from_zip(zip_file, 'keikoku_img00001.png')
        self.texture_warning_ch1 = [load_texture_from_zip(zip_file, 'keikoku_img00004.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00009.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00016.png')]
        self.texture_warning_ch1_base = load_texture_from_zip(zip_file, 'keikoku_img00002.png')
        self.texture_warning_ch2 = [load_texture_from_zip(zip_file, 'keikoku_img00005.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00006.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00007.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00008.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00010.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00011.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00012.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00013.png'),
                                    load_texture_from_zip(zip_file, 'keikoku_img00017.png')]
        self.texture_warning_ch2_base = load_texture_from_zip(zip_file, 'keikoku_img00003.png')
        self.texture_warning_bachi = load_texture_from_zip(zip_file, 'keikoku_img00019.png')
        self.texture_warning_bachi_hit = load_texture_from_zip(zip_file, 'keikoku_img00018.png')

        self.texture_warning_x_1 = load_texture_from_zip(zip_file, 'keikoku_img00014.png')
        self.texture_warning_x_2 = load_texture_from_zip(zip_file, 'keikoku_img00015.png')


        self.sound_bachi_swipe = ray.load_sound('Sounds\\title\\SE_ATTRACT_2.ogg')
        self.sound_bachi_hit = ray.load_sound('Sounds\\title\\SE_ATTRACT_3.ogg')
        self.sound_warning_message = ray.load_sound('Sounds\\title\\VO_ATTRACT_3.ogg')
        self.sound_warning_error = ray.load_sound('Sounds\\title\\SE_ATTRACT_1.ogg')

        self.texture_black = load_texture_from_zip('Graphics\\lumendata\\attract\\movie.zip', 'movie_img00000.png')

    def scene_manager(self):
        if self.current_op_video is not None:
            self.scene = 'Opening Video'
            self.current_op_video.update()
            if all(self.current_op_video.is_finished):
                self.current_op_video = None
                self.warning = WarningBoard(get_current_ms(), self)
        elif self.warning is not None:
            self.scene = 'Warning Board'
            self.warning.update(get_current_ms(), self)
            if self.warning.is_finished:
                self.warning = None
                self.current_attract_video = random.choice(self.attract_videos)
        elif self.current_attract_video is not None:
            self.scene = 'Attract Video'
            self.current_attract_video.update()
            if all(self.current_attract_video.is_finished):
                self.current_attract_video = None
                self.current_op_video = random.choice(self.op_videos)


    def update(self):
        self.scene_manager()
        if ray.is_key_pressed(ray.KeyboardKey.KEY_ENTER):
            return "ENTRY"
        return None

    def draw(self):
        if self.current_op_video is not None:
            self.current_op_video.draw()
        elif self.warning is not None:
            bg_source = ray.Rectangle(0, 0, self.texture_bg.width, self.texture_bg.height)
            bg_dest = ray.Rectangle(0, 0, self.width, self.height)
            ray.draw_texture_pro(self.texture_bg, bg_source, bg_dest, ray.Vector2(0,0), 0, ray.WHITE)
            self.warning.draw(self)
        elif self.current_attract_video is not None:
            self.current_attract_video.draw()

        ray.draw_text(f"Scene: {self.scene}", 20, 40, 20, ray.BLUE)

class WarningBoard:
    def __init__(self, current_ms, title_screen):
        self.start_ms = current_ms
        self.error_time = 4250

        #Move warning board down from top of screen
        self.move_animation_1 = Animation(current_ms, 266.67, 'move')
        self.move_animation_1.params['start_position'] = -720
        self.move_animation_1.params['total_distance'] = title_screen.height + ((title_screen.height - title_screen.texture_warning.height)//2) + 20

        #Move warning board up a little bit
        self.move_animation_2 = Animation(current_ms, 116.67, 'move')
        self.move_animation_2.params['start_position'] = 92 + 20
        self.move_animation_2.params['delay'] = 266.67
        self.move_animation_2.params['total_distance'] = -30

        #And finally into its correct position
        self.move_animation_3 = Animation(current_ms, 116.67, 'move')
        self.move_animation_3.params['start_position'] = 82
        self.move_animation_3.params['delay'] = 383.34
        self.move_animation_3.params['total_distance'] = 10

        self.fade_animation_1 = Animation(current_ms, 300, 'fade')
        self.fade_animation_1.params['delay'] = 266.67
        self.fade_animation_1.params['initial_opacity'] = 0.0
        self.fade_animation_1.params['final_opacity'] = 1.0

        #Fade to black
        self.fade_animation_2 = Animation(current_ms, 500, 'fade')
        self.fade_animation_2.params['initial_opacity'] = 0.0
        self.fade_animation_2.params['final_opacity'] = 1.0
        self.fade_animation_2.params['delay'] = 500

        self.fade_animation_3 = Animation(current_ms, 50, 'fade')
        self.fade_animation_3.params['delay'] = 16.67
        self.fade_animation_3.params['initial_opacity'] = 0.75

        self.resize_animation_1 = Animation(current_ms, 166.67, 'texture_resize')
        self.resize_animation_1.params['initial_size'] = 1.0
        self.resize_animation_1.params['final_size'] = 1.5
        self.resize_animation_1.params['delay'] = self.error_time
        self.resize_animation_1.params['reverse'] = 0

        self.fade_animation_4 = Animation(current_ms, 166.67, 'fade')
        self.fade_animation_4.params['delay'] = self.error_time
        self.fade_animation_4.params['initial_opacity'] = 0.0
        self.fade_animation_4.params['final_opacity'] = 1.0
        self.fade_animation_4.params['reverse'] = 166.67

        self.fade_animation_6 = Animation(current_ms, 166.67, 'fade')
        self.fade_animation_6.params['delay'] = self.error_time + 166.67 + 166.67
        self.fade_animation_6.params['initial_opacity'] = 0.0
        self.fade_animation_6.params['final_opacity'] = 1.0

        #Bachi hit
        self.resize_animation_3 = Animation(current_ms, 233.34, 'texture_resize')
        self.resize_animation_3.params['initial_size'] = 0.5
        self.resize_animation_3.params['final_size'] = 1.5

        #Bachi hit
        self.fade_animation_7 = Animation(current_ms, 116.67, 'fade')
        self.fade_animation_7.params['initial_opacity'] = 0.0
        self.fade_animation_7.params['final_opacity'] = 1.0
        self.fade_animation_7.params['reverse'] = 0

        self.source_rect = ray.Rectangle(0, 0, title_screen.texture_black.width, title_screen.texture_black.height)
        self.dest_rect = ray.Rectangle(0, 0, title_screen.width, title_screen.height)

        self.character_time = 0
        self.character_index_val = 0
        self.hit_played = False
        self.error_played = False
        self.is_finished = False

        self.attract_frame_index = 0

    def load_next_attract(self, title_screen):
        if title_screen.current_attract_video.convert_frames_background(self.attract_frame_index) == 0:
            return 0
        self.attract_frame_index += 1

    def update(self, current_ms, title_screen):
        self.move_animation_1.update(current_ms)
        self.move_animation_2.update(current_ms)
        self.move_animation_3.update(current_ms)
        self.fade_animation_1.update(current_ms)
        self.fade_animation_2.update(current_ms)
        self.fade_animation_3.update(current_ms)
        self.fade_animation_4.update(current_ms)
        self.fade_animation_6.update(current_ms)
        self.resize_animation_1.update(current_ms)
        delay = 566.67
        elapsed_time = current_ms - self.start_ms
        if self.character_index(1) != 8:
            self.fade_animation_2.params['delay'] = elapsed_time + 500
            if delay <= elapsed_time and not ray.is_sound_playing(title_screen.sound_bachi_swipe):
                ray.play_sound(title_screen.sound_warning_message)
                ray.play_sound(title_screen.sound_bachi_swipe)
        elif self.character_index(1) == 8:
            if not self.hit_played:
                self.hit_played = True
                ray.play_sound(title_screen.sound_bachi_hit)
                self.resize_animation_3.start_ms = current_ms
                self.fade_animation_7.start_ms = current_ms
            self.resize_animation_3.update(current_ms)
            self.fade_animation_7.update(current_ms)

        if self.error_time + 166.67 <= elapsed_time and not self.error_played:
            self.error_played = True
            ray.play_sound(title_screen.sound_warning_error)
        if self.fade_animation_2.is_finished:
            self.is_finished = True

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
            self.fade_animation_3.start_ms = get_current_ms()
            self.fade_animation_3.duration = int(animation[self.character_index_val][0])
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
        ray.draw_texture(title_screen.texture_warning_x_2, 150, 200, ray.fade(ray.WHITE, self.fade_animation_6.attribute))
        ray.draw_texture(title_screen.texture_warning_ch1_base, 135, int(y)+title_screen.texture_warning_ch1[0].height+110, fade_2)
        ray.draw_texture(title_screen.texture_warning_ch1[self.character_index(2)], 115, int(y)+150, fade)
        ray.draw_texture(title_screen.texture_warning_ch2_base, 360, int(y)+title_screen.texture_warning_ch2[0].height+60, fade_2)
        if 0 < self.character_index(1):
            ray.draw_texture(title_screen.texture_warning_ch2[self.character_index(1)-1], 315, int(y)+100, ray.fade(ray.WHITE, self.fade_animation_3.attribute))
        ray.draw_texture(title_screen.texture_warning_ch2[self.character_index(1)], 315, int(y)+100, fade)
        if self.character_index(1) == 8:
            ray.draw_texture(title_screen.texture_warning_bachi, 350, int(y)+135, ray.WHITE)

        scale = self.resize_animation_1.attribute
        width = title_screen.texture_warning_x_1.width
        height = title_screen.texture_warning_x_1.height
        x_x = 150 + (width//2) - ((width * scale)//2)
        x_y = 200 + (height//2) - ((height * scale)//2)
        x_source = ray.Rectangle(0, 0, width, height)
        x_dest = ray.Rectangle(x_x, x_y, width*scale, height*scale)
        ray.draw_texture_pro(title_screen.texture_warning_x_1, x_source, x_dest, ray.Vector2(0,0), 0, ray.fade(ray.WHITE, self.fade_animation_4.attribute))

        scale = self.resize_animation_3.attribute
        width = title_screen.texture_warning_bachi_hit.width
        height = title_screen.texture_warning_bachi_hit.height
        hit_x = 350 + (width//2) - ((width * scale)//2)
        hit_y = 225 + (height//2) - ((height * scale)//2)
        hit_source = ray.Rectangle(0, 0, width, height)
        hit_dest = ray.Rectangle(hit_x, hit_y, width*scale, height*scale)
        ray.draw_texture_pro(title_screen.texture_warning_bachi_hit, hit_source, hit_dest, ray.Vector2(0,0), 0, ray.fade(ray.WHITE, self.fade_animation_7.attribute))
        ray.draw_texture_pro(title_screen.texture_black, self.source_rect, self.dest_rect, ray.Vector2(0,0), 0, ray.fade(ray.WHITE, self.fade_animation_2.attribute))
