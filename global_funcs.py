import time
import os
import pyray as ray
import cv2
import math
import zipfile
import tempfile

from collections import deque

#TJA Format creator is unknown. I did not create the format, but I did write the parser though.

def load_image_from_zip(zip_path, filename):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        with zip_ref.open(filename) as image_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_file.write(image_file.read())
                temp_file_path = temp_file.name
        image = ray.load_image(temp_file_path)
        os.remove(temp_file_path)
        return image

def load_texture_from_zip(zip_path, filename):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        with zip_ref.open(filename) as image_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_file.write(image_file.read())
                temp_file_path = temp_file.name
        texture = ray.load_texture(temp_file_path)
        os.remove(temp_file_path)
        return texture

def rounded(num):
    sign = 1 if (num >= 0) else -1
    num = abs(num)
    result = int(num)
    if (num - result >= 0.5):
        result += 1
    return sign * result

def get_current_ms():
    return rounded(time.time() * 1000)

def stripComments(code):
    result = ''
    index = 0
    is_line = True
    for line in code.splitlines():
        comment_index = line.find('//')
        if comment_index == -1:
            result += line
            is_line = True
        elif comment_index != 0 and not line[:comment_index].isspace():
            result += line[:comment_index]
            is_line = True
        else:
            is_line = False
        index += 1
    return result

def get_pixels_per_frame(bpm, time_signature, distance):
    beat_duration = 60 / bpm
    total_time = time_signature * beat_duration
    total_frames = 60 * total_time
    return (distance / total_frames)

def calculate_base_score(play_note_list):
    total_notes = 0
    balloon_num = 0
    balloon_sec = 0
    balloon_count = 0
    drumroll_sec = 0
    for i in range(len(play_note_list)):
        note = play_note_list[i]
        if i < len(play_note_list)-1:
            next_note = play_note_list[i+1]
        else:
            next_note = play_note_list[len(play_note_list)-1]
        if note.get('note') in {'1','2','3','4'}:
            total_notes += 1
        elif note.get('note') in {'5', '6'}:
            drumroll_sec += (next_note.get('ms') - note.get('ms')) / 1000
        elif note.get('note') in {'7', '9'}:
            balloon_num += 1
            balloon_count += next_note.get('balloon')
    total_score = (1000000 - (balloon_count * 100) - (drumroll_sec * 1692.0079999994086)) / total_notes
    return math.ceil(total_score / 10) * 10

class TJAParser:
    def __init__(self, path):
        #Defined on startup
        self.folder_path = path
        self.folder_name = self.folder_path.split('\\')[-1]
        self.file_path = f'{self.folder_path}\\{self.folder_name}.tja'

        #Defined on file_to_data()
        self.data = []

        #Defined on get_metadata()
        self.title = ''
        self.title_ja = ''
        self.subtitle = ''
        self.subtitle_ja = ''
        self.wave = f'{self.folder_path}\\'
        self.offset = 0
        self.demo_start = 0
        self.course_data = dict()

        #Defined in metadata but can change throughout the chart
        self.bpm = 120
        self.time_signature = 4/4

        self.distance = 0
        self.scroll_modifier = 1
        self.current_ms = 0
        self.barline_display = True
        self.gogo_time = False

    def file_to_data(self):
        with open(self.file_path, 'rt', encoding='utf-8-sig') as tja_file:
            for line in tja_file:
                line = stripComments(line).strip()
                if line != '':
                    self.data.append(str(line))
            return self.data

    def get_metadata(self):
        self.file_to_data()
        diff_index = 1
        highest_diff = -1
        for item in self.data:
            if item[0] == '#':
                continue
            elif 'SUBTITLEJA' in item: self.subtitle_ja = str(item.split('SUBTITLEJA:')[1])
            elif 'TITLEJA' in item: self.title_ja = str(item.split('TITLEJA:')[1])
            elif 'SUBTITLE' in item: self.subtitle = str(item.split('SUBTITLE:')[1][2:])
            elif 'TITLE' in item: self.title = str(item.split('TITLE:')[1])
            elif 'BPM' in item: self.bpm = float(item.split(':')[1])
            elif 'WAVE' in item: self.wave += str(item.split(':')[1])
            elif 'OFFSET' in item: self.offset = float(item.split(':')[1])
            elif 'DEMOSTART' in item: self.demo_start = float(item.split(':')[1])
            elif 'COURSE' in item:
                course = str(item.split(':')[1]).lower()
                if course == 'tower' or course == '6':
                    self.course_data[6] = []
                if course == 'dan' or course == '5':
                    self.course_data[5] = []
                elif course == 'edit' or course == '4':
                    self.course_data[4] = []
                elif course == 'oni' or course == '3':
                    self.course_data[3] = []
                elif course == 'hard' or course == '2':
                    self.course_data[2] = []
                elif course == 'normal' or course == '1':
                    self.course_data[1] = []
                elif course == 'easy' or course == '0':
                    self.course_data[0] = []
                highest_diff = max(self.course_data)
                diff_index -= 1
            elif 'LEVEL' in item:
                item = int(item.split(':')[1])
                self.course_data[diff_index+highest_diff].append(item)
            elif 'BALLOON' in item:
                item = item.split(':')[1]
                if item == '':
                    continue
                self.course_data[diff_index+highest_diff].append([int(x) for x in item.split(',')])
            elif 'SCOREINIT' in item:
                if item.split(':')[1] == '':
                    continue
                item = item.split(':')[1]
                self.course_data[diff_index+highest_diff].append([int(x) for x in item.split(',')])
            elif 'SCOREDIFF' in item:
                if item.split(':')[1] == '':
                    continue
                item = int(item.split(':')[1])
                self.course_data[diff_index+highest_diff].append(item)
        return [self.title, self.title_ja, self.subtitle, self.subtitle_ja,
            self.bpm, self.wave, self.offset, self.demo_start, self.course_data]

    def data_to_notes(self, diff):
        self.file_to_data()
        #Get notes start and end
        note_start = -1
        note_end = -1
        diff_count = 0
        for i in range(len(self.data)):
            if self.data[i] == '#START':
                note_start = i+1
            elif self.data[i] == '#END':
                note_end = i
                diff_count += 1
            if diff_count == len(self.course_data) - diff:
                break

        notes = []
        bar = []
        #Check for measures and separate when comma exists
        for i in range(note_start, note_end):
            item = self.data[i].strip(',')
            bar.append(item)
            if item != self.data[i]:
                notes.append(bar)
                bar = []
        return notes, self.course_data[diff][1]

    def get_se_note(self, play_note_list, ms_per_measure, note, note_ms):
        #Someone please refactor this
        se_notes = {'1': [0, 1, 2],
            '2': [3, 4],
            '3': 5,
            '4': 6,
            '5': 7,
            '6': 14,
            '7': 9,
            '8': 10,
            '9': 11}
        if len(play_note_list) > 1:
            prev_note = play_note_list[-2]
            if prev_note['note'] in {'1', '2'}:
                if note_ms - prev_note['ms'] <= (ms_per_measure/8) - 1:
                    prev_note['se_note'] = se_notes[prev_note['note']][1]
                else:
                    prev_note['se_note'] = se_notes[prev_note['note']][0]
            else:
                prev_note['se_note'] = se_notes[prev_note['note']]
            if len(play_note_list) > 3:
                if play_note_list[-4]['note'] == play_note_list[-3]['note'] == play_note_list[-2]['note'] == '1':
                    if (play_note_list[-3]['ms'] - play_note_list[-4]['ms'] < (ms_per_measure/8)) and (play_note_list[-2]['ms'] - play_note_list[-3]['ms'] < (ms_per_measure/8)):
                        if len(play_note_list) > 5:
                            if (play_note_list[-4]['ms'] - play_note_list[-5]['ms'] >= (ms_per_measure/8)) and (play_note_list[-1]['ms'] - play_note_list[-2]['ms'] >= (ms_per_measure/8)):
                                play_note_list[-3]['se_note'] = se_notes[play_note_list[-3]['note']][2]
                        else:
                            play_note_list[-3]['se_note'] = se_notes[play_note_list[-3]['note']][2]
        else:
            play_note_list[-1]['se_note'] = se_notes[note]
        if play_note_list[-1]['note'] in {'1', '2'}:
            play_note_list[-1]['se_note'] = se_notes[note][0]
        else:
            play_note_list[-1]['se_note'] = se_notes[note]

    def notes_to_position(self, diff):
        play_note_list = deque()
        bar_list = deque()
        draw_note_list = deque()
        notes, balloon = self.data_to_notes(diff)
        index = 0
        balloon_index = 0
        drumroll_head = dict()
        drumroll_tail = dict()
        for bar in notes:
            #Length of the bar is determined by number of notes excluding commands
            bar_length = sum(len(part) for part in bar if '#' not in part)

            for part in bar:
                if '#JPOSSCROLL' in part:
                    continue
                elif '#NMSCROLL' in part:
                    continue
                elif '#MEASURE' in part:
                    divisor = part.find('/')
                    self.time_signature = float(part[9:divisor]) / float(part[divisor+1:])
                    continue
                elif '#SCROLL' in part:
                    self.scroll_modifier = float(part[7:])
                    continue
                elif '#BPMCHANGE' in part:
                    self.bpm = float(part[11:])
                    continue
                elif '#BARLINEOFF' in part:
                    self.barline_display = False
                    continue
                elif '#BARLINEON' in part:
                    self.barline_display = True
                    continue
                elif '#GOGOSTART' in part:
                    self.gogo_time = True
                    continue
                elif '#GOGOEND' in part:
                    self.gogo_time = False
                    continue
                elif '#LYRIC' in part:
                    continue
                #Unrecognized commands will be skipped for now
                elif '#' in part:
                    continue

                #https://gist.github.com/KatieFrogs/e000f406bbc70a12f3c34a07303eec8b#measure
                ms_per_measure = 60000 * (self.time_signature*4) / self.bpm

                #Determines how quickly the notes need to move across the screen to reach the judgment circle in time
                pixels_per_frame = get_pixels_per_frame(self.bpm * self.time_signature * self.scroll_modifier, self.time_signature*4, self.distance)
                pixels_per_ms = pixels_per_frame / (1000 / 60)

                bar_ms = self.current_ms
                load_ms = bar_ms - (self.distance / pixels_per_ms)

                if self.barline_display:
                    bar_list.append({'note': 'barline', 'ms': bar_ms, 'load_ms': load_ms, 'ppf': pixels_per_frame})

                #Empty bar is still a bar, otherwise start increment
                if len(part) == 0:
                    self.current_ms += ms_per_measure
                    increment = 0
                else:
                    increment = ms_per_measure / bar_length

                for note in part:
                    note_ms = self.current_ms
                    load_ms = note_ms - (self.distance / pixels_per_ms)
                    #Do not add blank notes otherwise lag
                    if note != '0':
                        play_note_list.append({'note': note, 'ms': note_ms, 'load_ms': load_ms, 'ppf': pixels_per_frame, 'index': index})
                        self.get_se_note(play_note_list, ms_per_measure, note, note_ms)
                        index += 1
                    if note in {'5', '6', '8'}:
                        play_note_list[-1]['color'] = 255
                    if note == '8' and play_note_list[-2]['note'] in ('7', '9'):
                        if balloon_index >= len(balloon):
                            play_note_list[-1]['balloon'] = 0
                        else:
                            play_note_list[-1]['balloon'] = int(balloon[balloon_index])
                        balloon_index += 1
                    self.current_ms += increment

        # https://stackoverflow.com/questions/72899/how-to-sort-a-list-of-dictionaries-by-a-value-of-the-dictionary-in-python
        # Sorting by load_ms is necessary for drawing, as some notes appear on the
        # screen slower regardless of when they reach the judge circle
        # Bars can be sorted like this because they don't need hit detection
        draw_note_list = deque(sorted(play_note_list, key=lambda d: d['load_ms']))
        bar_list = deque(sorted(bar_list, key=lambda d: d['load_ms']))
        return play_note_list, draw_note_list, bar_list

class Animation:
    def __init__(self, current_ms, duration, type):
        self.type = type
        self.start_ms = current_ms
        self.attribute = 0
        self.duration = duration
        self.params = dict()
        self.is_finished = False

    def update(self, current_ms):
        if self.type == 'fade':
            self.fade(current_ms,
                self.duration,
                initial_opacity=self.params.get('initial_opacity', 1.0),
                final_opacity=self.params.get('final_opacity', 0.0),
                delay=self.params.get('delay', 0.0),
                ease_in=self.params.get('ease_in', None),
                ease_out=self.params.get('ease_out', None))
            if self.params.get('reverse', None) is not None and current_ms - self.start_ms >= self.duration + self.params.get('delay', 0.0):
                self.fade(current_ms,
                    self.duration,
                    final_opacity=self.params.get('initial_opacity', 1.0),
                    initial_opacity=self.params.get('final_opacity', 0.0),
                    delay=self.params.get('delay', 0.0) + self.duration + self.params.get('reverse'),
                    ease_in=self.params.get('ease_in', None),
                    ease_out=self.params.get('ease_out', None))
        elif self.type == 'move':
            self.move(current_ms,
                self.duration,
                self.params['total_distance'],
                self.params['start_position'],
                delay=self.params.get('delay', 0.0))
        elif self.type == 'texture_change':
            self.texture_change(current_ms,
                self.duration,
                self.params['textures'])
        elif self.type == 'text_stretch':
            self.text_stretch(current_ms,
                self.duration)
        elif self.type == 'texture_resize':
            self.texture_resize(current_ms,
                self.duration,
                initial_size=self.params.get('initial_size', 1.0),
                final_size=self.params.get('final_size', 1.0),
                delay=self.params.get('delay', 0.0))
            if self.params.get('reverse', None) is not None and current_ms - self.start_ms >= self.duration + self.params.get('delay', 0.0):
                self.texture_resize(current_ms,
                    self.duration,
                    final_size=self.params.get('initial_size', 1.0),
                    initial_size=self.params.get('final_size', 1.0),
                    delay=self.params.get('delay', 0.0) + self.duration)

    def fade(self, current_ms, duration, initial_opacity, final_opacity, delay, ease_in, ease_out):
        def ease_out_progress(progress, ease):
            if ease == 'quadratic':
                return progress * (2 - progress)
            elif ease == 'cubic':
                return 1 - pow(1 - progress, 3)
            elif ease == 'exponential':
                return 1 - pow(2, -10 * progress)
            else:
                return progress
        def ease_in_progress(progress, ease):
            if ease == 'quadratic':
                return progress * progress
            elif ease == 'cubic':
                return progress * progress * progress
            elif ease == 'exponential':
                return pow(2, 10 * (progress - 1))
            else:
                return progress
        elapsed_time = current_ms - self.start_ms
        if elapsed_time < delay:
            self.attribute = initial_opacity

        elapsed_time -= delay
        if elapsed_time >= duration:
            self.attribute = final_opacity
            self.is_finished = True

        if ease_in is not None:
            progress = ease_in_progress(elapsed_time / duration, ease_in)
        elif ease_out is not None:
            progress = ease_out_progress(elapsed_time / duration, ease_out)
        else:
            progress = elapsed_time / duration

        current_opacity = initial_opacity + (final_opacity - initial_opacity) * progress
        self.attribute = current_opacity
    def move(self, current_ms, duration, total_distance, start_position, delay):
        elapsed_time = current_ms - self.start_ms
        if elapsed_time < delay:
            self.attribute = start_position

        elapsed_time -= delay
        if elapsed_time <= duration:
            progress = elapsed_time / duration
            self.attribute = start_position + (total_distance * progress)
        else:
            self.attribute = start_position + total_distance
            self.is_finished = True
    def texture_change(self, current_ms, duration, textures):
        elapsed_time = current_ms - self.start_ms
        if elapsed_time <= duration:
            for start, end, index in textures:
                if start < elapsed_time <= end:
                    self.attribute = index
        else:
            self.is_finished = True
    def text_stretch(self, current_ms, duration):
        elapsed_time = current_ms - self.start_ms
        if elapsed_time <= duration:
            self.attribute = 2 + 5 * (elapsed_time // 25)
        elif elapsed_time <= duration + 116:
            frame_time = (elapsed_time - duration) // 16.57
            self.attribute = 2 + 10 - (2 * (frame_time + 1))
        else:
            self.attribute = 0
            self.is_finished = True
    def texture_resize(self, current_ms, duration, initial_size, final_size, delay):
        elapsed_time = current_ms - self.start_ms
        if elapsed_time < delay:
            self.attribute = initial_size
        elapsed_time -= delay
        if elapsed_time >= duration:
            self.attribute = final_size
            self.is_finished = True
        elif elapsed_time < duration:
            progress = elapsed_time / duration
            self.attribute = initial_size + ((final_size - initial_size) * progress)
        else:
            self.attribute = final_size
            self.is_finished = True

class VideoPlayer:
    def __init__(self, path, loop_start=None):
        self.video_path = path
        self.start_ms = None
        self.loop_start = loop_start

        self.current_frame = None
        self.last_frame = self.current_frame
        self.frame_index = 0
        self.frames = []
        self.cap = cv2.VideoCapture(self.video_path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)

        self.is_finished = [False, False]
        audio_path = path[:-4] + '.ogg'
        self.audio = ray.load_music_stream(audio_path)

    def convert_frames_background(self, index):
        if not self.cap.isOpened():
            raise ValueError("Error: Could not open video file.")

        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if len(self.frames) == total_frames:
            return 0
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)

        success, frame = self.cap.read()

        timestamp = (index / self.fps * 1000)
        frame_rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        new_frame = ray.Image(frame_rgb.tobytes(), frame_rgb.shape[1], frame_rgb.shape[0], 1, ray.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8)

        self.frames.append((timestamp, new_frame))
        print(len(self.frames), total_frames)

    def convert_frames(self):
        if not self.cap.isOpened():
            raise ValueError("Error: Could not open video file.")

        frame_count = 0
        success, frame = self.cap.read()

        while success:
            timestamp = (frame_count / self.fps * 1000)
            frame_rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            new_frame = ray.Image(frame_rgb.tobytes(), frame_rgb.shape[1], frame_rgb.shape[0], 1, ray.PixelFormat.PIXELFORMAT_UNCOMPRESSED_R8G8B8)

            self.frames.append((timestamp, new_frame))

            success, frame = self.cap.read()
            frame_count += 1

        self.cap.release()
        print(f"Extracted {len(self.frames)} frames.")
        self.start_ms = get_current_ms()

    def check_for_start(self):
        if self.start_ms is None:
            self.start_ms = get_current_ms()
            ray.play_music_stream(self.audio)
        if self.frames == []:
            self.convert_frames()

    def audio_manager(self):
        ray.update_music_stream(self.audio)
        time_played = ray.get_music_time_played(self.audio) / ray.get_music_time_length(self.audio)
        ending_lenience = 0.95
        if time_played > ending_lenience:
            self.is_finished[1] = True

    def update(self):
        self.check_for_start()
        self.audio_manager()

        if self.frame_index == len(self.frames)-1:
            self.is_finished[0] = True
            return

        if self.start_ms is None:
            return

        timestamp, frame = self.frames[self.frame_index][0], self.frames[self.frame_index][1]
        elapsed_time = get_current_ms() - self.start_ms
        if elapsed_time >= timestamp:
            self.current_frame = ray.load_texture_from_image(frame)
            if self.last_frame != self.current_frame and self.last_frame is not None:
                ray.unload_texture(self.last_frame)
            self.frame_index += 1
            self.last_frame = self.current_frame

    def draw(self):
        if self.current_frame is not None:
            ray.draw_texture(self.current_frame, 0, 0, ray.WHITE)

    def __del__(self):
        if hasattr(self, 'current_frame') and self.current_frame:
            ray.unload_texture(self.current_frame)
        if hasattr(self, 'last_frame') and self.last_frame:
            ray.unload_texture(self.last_frame)
