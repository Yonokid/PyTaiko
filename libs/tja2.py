import bisect
from enum import IntEnum
import hashlib
from dataclasses import dataclass, field, fields

from libs.tja import NoteList, TJAParser, TimelineObject, get_ms_per_measure

class NoteType(IntEnum):
    NONE = 0
    DON = 1
    KAT = 2
    DON_L = 3
    KAT_L = 4
    ROLL_HEAD = 5
    ROLL_HEAD_L = 6
    BALLOON_HEAD = 7
    TAIL = 8
    KUSUDAMA = 9

class ScrollType(IntEnum):
    NMSCROLL = 0
    BMSCROLL = 1
    HBSCROLL = 2

@dataclass()
class Note:
    type: int = field(init=False)
    hit_ms: float = field(init=False)
    display: bool = field(init=False)
    index: int = field(init=False)
    moji: int = field(init=False)
    bpm: float = field(init=False)
    scroll_x: float = field(init=False)
    scroll_y: float = field(init=False)

    def __lt__(self, other):
        return self.hit_ms < other.hit_ms

    def __le__(self, other):
        return self.hit_ms <= other.hit_ms

    def __gt__(self, other):
        return self.hit_ms > other.hit_ms

    def __ge__(self, other):
        return self.hit_ms >= other.hit_ms

    def __eq__(self, other):
        return self.hit_ms == other.hit_ms

    def _get_hash_data(self) -> bytes:
        hash_fields = ['type', 'hit_ms']
        field_values = []

        for field_name in sorted(hash_fields):
            value = getattr(self, field_name, None)
            field_values.append((field_name, value))

        field_values.append(('__class__', self.__class__.__name__))
        hash_string = str(field_values)
        return hash_string.encode('utf-8')

    def get_hash(self, algorithm='sha256') -> str:
        """Generate hash of the note"""
        hash_obj = hashlib.new(algorithm)
        hash_obj.update(self._get_hash_data())
        return hash_obj.hexdigest()

    def __hash__(self) -> int:
        """Make instances hashable for use in sets/dicts"""
        return int(self.get_hash('md5')[:8], 16)  # Use first 8 chars of MD5 as int

    def __repr__(self):
        return str(self.__dict__)

@dataclass
class Drumroll(Note):
    """A drumroll note in a TJA file.

    Attributes:
        _source_note (Note): The source note.
        color (int): The color of the drumroll. (0-255 where 255 is red)
    """
    _source_note: Note
    color: int = field(init=False)

    def __repr__(self):
        return str(self.__dict__)

    def __eq__(self, other):
        return self.hit_ms == other.hit_ms

    def __post_init__(self):
        for field_name in [f.name for f in fields(Note)]:
            if hasattr(self._source_note, field_name):
                setattr(self, field_name, getattr(self._source_note, field_name))

@dataclass
class Balloon(Note):
    """A balloon note in a TJA file.

    Attributes:
        _source_note (Note): The source note.
        count (int): The number of hits it takes to pop.
        popped (bool): Whether the balloon has been popped.
        is_kusudama (bool): Whether the balloon is a kusudama.
    """
    _source_note: Note
    count: int = field(init=False)
    popped: bool = False
    is_kusudama: bool = False

    def __repr__(self):
        return str(self.__dict__)

    def __eq__(self, other):
        return self.hit_ms == other.hit_ms

    def __post_init__(self):
        for field_name in [f.name for f in fields(Note)]:
            if hasattr(self._source_note, field_name):
                setattr(self, field_name, getattr(self._source_note, field_name))

    def _get_hash_data(self) -> bytes:
        """Override to include source note and balloon-specific data"""
        hash_fields = ['type', 'hit_ms', 'load_ms', 'count']
        field_values = []

        for field_name in sorted(hash_fields):
            value = getattr(self, field_name, None)
            field_values.append((field_name, value))

        field_values.append(('__class__', self.__class__.__name__))
        hash_string = str(field_values)
        return hash_string.encode('utf-8')

class TJAParser2(TJAParser):
    def notes_to_position(self, diff: int):
        """Parse a TJA's notes into a NoteList."""
        master_notes = NoteList()
        notes = self.data_to_notes(diff)
        balloon = self.metadata.course_data[diff].balloon.copy()
        count = 0
        index = 0
        time_signature = 4/4
        bpm = self.metadata.bpm
        scroll_x_modifier = 1
        scroll_y_modifier = 0
        barline_display = True
        curr_note_list = master_notes.play_notes
        curr_draw_list = master_notes.draw_notes
        curr_bar_list = master_notes.bars
        curr_timeline = master_notes.timeline
        init_bpm = TimelineObject()
        init_bpm.hit_ms = self.current_ms
        init_bpm.bpm = bpm
        curr_timeline.append(init_bpm)
        prev_note = None
        scroll_type = ScrollType.NMSCROLL

        bpmchange_last_bpm = bpm

        for bar in notes:
            bar_length = sum(len(part) for part in bar if '#' not in part)
            barline_added = False

            for part in bar:
                if '#MEASURE' in part:
                    divisor = part.find('/')
                    time_signature = float(part[9:divisor]) / float(part[divisor+1:])
                    continue
                elif '#SCROLL' in part:
                    if scroll_type != ScrollType.BMSCROLL:
                        scroll_value = part[7:]
                        if 'i' in scroll_value:
                            normalized = scroll_value.replace('.i', 'j').replace('i', 'j')
                            normalized = normalized.replace(',', '')
                            c = complex(normalized)
                            scroll_x_modifier = c.real
                            scroll_y_modifier = c.imag
                        else:
                            scroll_x_modifier = float(scroll_value)
                            scroll_y_modifier = 0.0
                    continue
                elif '#BPMCHANGE' in part:
                    parsed_bpm = float(part[11:])
                    if scroll_type == ScrollType.BMSCROLL or scroll_type == ScrollType.HBSCROLL:
                        # Do not modify bpm, it needs to be changed live by bpmchange
                        bpmchange = parsed_bpm / bpmchange_last_bpm
                        bpmchange_last_bpm = parsed_bpm

                        bpmchange_timeline = TimelineObject()
                        bpmchange_timeline.hit_ms = self.current_ms
                        bpmchange_timeline.bpmchange = bpmchange
                        bisect.insort(curr_timeline, bpmchange_timeline, key=lambda x: x.hit_ms)
                    else:
                        timeline_obj = TimelineObject()
                        timeline_obj.hit_ms = self.current_ms
                        timeline_obj.bpm = parsed_bpm
                        bpm = parsed_bpm
                        bisect.insort(curr_timeline, timeline_obj, key=lambda x: x.hit_ms)
                    continue
                elif len(part) > 0 and not part[0].isdigit():
                    continue

                ms_per_measure = get_ms_per_measure(bpm, time_signature)
                bar_line = Note()

                bar_line.hit_ms = self.current_ms
                bar_line.type = 0
                bar_line.display = barline_display
                bar_line.bpm = bpm
                bar_line.scroll_x = scroll_x_modifier
                bar_line.scroll_y = scroll_y_modifier

                if barline_added:
                    bar_line.display = False

                curr_bar_list.append(bar_line)
                barline_added = True

                if len(part) == 0:
                    self.current_ms += ms_per_measure
                    increment = 0
                else:
                    increment = ms_per_measure / bar_length

                for item in part:
                    if item == '0' or (not item.isdigit()):
                        self.current_ms += increment
                        continue

                    note = Note()
                    note.hit_ms = self.current_ms
                    note.display = True
                    note.type = int(item)
                    note.index = index
                    note.bpm = bpm
                    note.scroll_x = scroll_x_modifier
                    note.scroll_y = scroll_y_modifier

                    if item in {'5', '6'}:
                        note = Drumroll(note)
                        note.color = 255
                    elif item in {'7', '9'}:
                        count += 1
                        if balloon is None:
                            raise Exception("Balloon note found, but no count was specified")
                        if item == '9':
                            note = Balloon(note, is_kusudama=True)
                        else:
                            note = Balloon(note)
                        note.count = 1 if not balloon else balloon.pop(0)
                    elif item == '8':
                        if prev_note is None:
                            raise ValueError("No previous note found")

                    self.current_ms += increment
                    curr_note_list.append(note)
                    curr_draw_list.append(note)
                    self.get_moji(curr_note_list, ms_per_measure)
                    index += 1
                    prev_note = note

        return master_notes, [master_notes], [master_notes], [master_notes]
