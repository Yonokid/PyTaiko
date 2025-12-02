import bisect
import hashlib
from dataclasses import dataclass, field, fields
from typing_extensions import Optional

from libs.tja import NoteList, ScrollType, TJAParser, TimelineObject, get_ms_per_measure

@dataclass()
class Note:
    type: int = field(init=False)
    hit_ms: float = field(init=False)
    bpm: float = field(init=False)
    scroll_x: float = field(init=False)
    scroll_y: float = field(init=False)
    display: bool = field(init=False)
    index: int = field(init=False)
    moji: int = field(init=False)

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

@dataclass
class ParserState:
    time_signature: float = 4/4
    bpm: float = 120
    bpmchange_last_bpm: float = 120
    scroll_x_modifier: float = 1
    scroll_y_modifier: float = 0
    scroll_type: ScrollType = ScrollType.NMSCROLL
    barline_display: bool = True
    curr_note_list: list[Note | Drumroll | Balloon] = []
    curr_draw_list: list[Note | Drumroll | Balloon] = []
    curr_bar_list: list[Note] = []
    curr_timeline: list[TimelineObject] = []
    index: int = 0
    balloons: list[int] = []
    balloon_index: int = 0
    prev_note: Optional[Note] = None
    barline_added: bool = False


class TJAParser2(TJAParser):
    def _build_command_registry(self):
        """Auto-discover command handlers based on naming convention."""
        registry = {}
        for name in dir(self):
            if name.startswith('handle_'):
                cmd_name = '#' + name[7:].upper()
                registry[cmd_name] = getattr(self, name)
        return registry

    def handle_measure(self, part: str, state: ParserState):
        numerator, denominator = part.split('/')
        state.time_signature = float(numerator) / float(denominator)

    def handle_scroll(self, part: str, state: ParserState):
        if 'i' in part:
            normalized = part.replace('.i', 'j').replace('i', 'j')
            normalized = normalized.replace(',', '')
            c = complex(normalized)
            state.scroll_x_modifier = c.real
            state.scroll_y_modifier = c.imag
        else:
            state.scroll_x_modifier = float(part)
            state.scroll_y_modifier = 0.0

    def handle_bpmchange(self, part: str, state: ParserState):
        parsed_bpm = float(part)
        if state.scroll_type == ScrollType.BMSCROLL or state.scroll_type == ScrollType.HBSCROLL:
            # Do not modify bpm, it needs to be changed live by bpmchange
            bpmchange = parsed_bpm / state.bpmchange_last_bpm
            state.bpmchange_last_bpm = parsed_bpm

            bpmchange_timeline = TimelineObject()
            bpmchange_timeline.hit_ms = self.current_ms
            bpmchange_timeline.bpmchange = bpmchange
            state.curr_timeline.append(bpmchange_timeline)
        else:
            timeline_obj = TimelineObject()
            timeline_obj.hit_ms = self.current_ms
            timeline_obj.bpm = parsed_bpm
            state.bpm = parsed_bpm
            state.curr_timeline.append(timeline_obj)

    def add_bar(self, state: ParserState):
        bar_line = Note()

        bar_line.hit_ms = self.current_ms
        bar_line.type = 0
        bar_line.display = state.barline_display
        bar_line.bpm = state.bpm
        bar_line.scroll_x = state.scroll_x_modifier
        bar_line.scroll_y = state.scroll_y_modifier

        if state.barline_added:
            bar_line.display = False

        return bar_line

    def add_note(self, item: str, state: ParserState):
        note = Note()
        note.hit_ms = self.current_ms
        note.display = True
        note.type = int(item)
        note.index = state.index
        note.bpm = state.bpm
        note.scroll_x = state.scroll_x_modifier
        note.scroll_y = state.scroll_y_modifier

        if item in {'5', '6'}:
            note = Drumroll(note)
            note.color = 255
        elif item in {'7', '9'}:
            state.balloon_index += 1
            if state.balloons is None:
                raise Exception("Balloon note found, but no count was specified")
            if item == '9':
                note = Balloon(note, is_kusudama=True)
            else:
                note = Balloon(note)
            note.count = 1 if not state.balloons else state.balloons.pop(0)
        elif item == '8':
            if state.prev_note is None:
                raise ValueError("No previous note found")

        return note

    def notes_to_position(self, diff: int):
        """Parse a TJA's notes into a NoteList."""
        commands = self._build_command_registry()
        master_notes = NoteList()
        notes = self.data_to_notes(diff)

        state = ParserState()
        state.bpm = self.metadata.bpm
        state.bpmchange_last_bpm = self.metadata.bpm
        state.balloons = self.metadata.course_data[diff].balloon.copy()
        state.curr_note_list = master_notes.play_notes
        state.curr_draw_list = master_notes.draw_notes
        state.curr_bar_list = master_notes.bars
        state.curr_timeline = master_notes.timeline

        init_bpm = TimelineObject()
        init_bpm.hit_ms = self.current_ms
        init_bpm.bpm = state.bpm
        state.curr_timeline.append(init_bpm)

        for bar in notes:
            bar_length = sum(len(part) for part in bar if '#' not in part)
            state.barline_added = False

            for part in bar:
                if part.startswith('#'):
                    for cmd_prefix, handler in commands.items():
                        if part.startswith(cmd_prefix):
                            value = part[len(cmd_prefix):].strip()
                            handler(value, state)
                            break
                    continue
                elif len(part) > 0 and not part[0].isdigit():
                    continue

                ms_per_measure = get_ms_per_measure(state.bpm, state.time_signature)

                bar = self.add_bar(state)
                state.curr_bar_list.append(bar)
                state.barline_added = True

                if len(part) == 0:
                    self.current_ms += ms_per_measure
                    increment = 0
                else:
                    increment = ms_per_measure / bar_length

                for item in part:
                    if item == '0' or (not item.isdigit()):
                        self.current_ms += increment
                        continue

                    note = self.add_note(item, state)

                    self.current_ms += increment
                    state.curr_note_list.append(note)
                    state.curr_draw_list.append(note)
                    self.get_moji(state.curr_note_list, ms_per_measure)
                    state.index += 1
                    state.prev_note = note

        return master_notes, [master_notes], [master_notes], [master_notes]
