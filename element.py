"""
Abstract::

This file defines all elements in the Arcaea chart file (aff).
Definition extracted from https://wiki.arcaea.cn

Each element provides a minimal syntax check, but it is not perfect,
so please DO NOT rely on it too much.
"""

__all__ = [
    'Command', 'Chart',
    'Note', 'Control',
    'Tap', 'Hold', 'Arc', 'ArcTap', 'Flick',
    'Timing', 'Camera', 'SceneControl', 'TimingGroup',
]

from abc import ABC, abstractmethod
from typing import Union, Optional, Type, TypeVar
from itertools import chain
from aff_token import AffToken, Color

_T = TypeVar('_T', bound='Command')


class Command(ABC):

    @abstractmethod
    def syntax_check(self) -> bool:
        """Basic syntax check of a command."""
        raise NotImplementedError

    @abstractmethod
    def get_interval(self) -> tuple[int, int]:
        """Return the interval (start and end time) of this command."""
        raise NotImplementedError


class Chart(object):
    """Arcaea chart."""

    def __init__(self, header_dict: dict, command_list: list['Command']):
        self.header_dict = header_dict
        self.command_list = command_list
        self._sorted_timing_list = sorted(
            self.get_command_list_for_type(Timing),
            key=lambda _: _.t
        )  # ignore the ones in timing groups

    def _get_note_bpm(self, note: 'Note') -> 'Timing':
        """Return the BPM corresponding to the (start time of the) note."""
        start_time = note.get_interval()[0]
        for timing in self._sorted_timing_list:
            if timing.t <= start_time:
                return timing

    def _return_connected_arc_list(self) -> list['Arc']:
        """
        Analyze the first and last cases of all Arc and return a list of
        Arc after assigning the correct value to 'has_head' attribute.
        """
        arc_list = filter(
            lambda _: not _.is_skyline,
            self.get_command_list_for_type(Arc)
        )
        arc_list_start_sorted = sorted(
            arc_list,
            key=lambda _: _.get_interval()[0]
        )  # listed in ascending order by Arc start timing
        arc_list_end_sorted = sorted(
            arc_list_start_sorted,
            key=lambda _: _.get_interval()[1]
        )  # listed in ascending order by Arc end timing

        length = len(arc_list_start_sorted)
        i = 0
        for arc in arc_list_start_sorted:
            for j in range(i, length):
                arc_prev = arc_list_end_sorted[j]
                if arc_prev.t2 <= arc.t1 - 10:
                    i = j
                elif arc_prev.t2 >= arc.t1 + 10:
                    break
                elif arc_prev != arc and arc.y1 == arc_prev.y2 and abs(arc.x1 - arc_prev.x2) <= 0.1:
                    arc.has_head = False  # they meet

        return arc_list_start_sorted

    def get_density_factor(self) -> float:
        """
        Return the value of timing point density factor of the chart.
        If the chart does not define a density factor, return 1.
        """
        return float(self.header_dict.get(AffToken.Keyword.timing_point_density_factor, 1.0))

    def get_command_list_for_type(self, type_: Type[_T], search_in_timing_group: bool = False) -> list[_T]:
        """Return a list of commands of the given type."""
        if type_ == ArcTap:
            list_of_arctap_list = [arc.arctap_list for arc in self.command_list if isinstance(arc, Arc)]
            list_in_chart = list(chain(*list_of_arctap_list))
        else:
            list_in_chart = [command for command in self.command_list if isinstance(command, type_)]

        if search_in_timing_group:
            list_in_timing_group = list(chain(*[
                timing_group.get_command_list_for_type(type_)
                for timing_group in self.get_command_list_for_type(TimingGroup)
            ]))

            return list_in_chart + list_in_timing_group

        return list_in_chart

    def get_long_note_combo(self, note_list: list['LongNote']) -> int:
        """Return the total combo of the LongNote (Hold or Arc)."""
        density_factor = self.get_density_factor()
        result = 0

        for long_note in note_list:
            bpm = self._get_note_bpm(long_note).bpm
            start_time, end_time = long_note.get_interval()
            if bpm == 0 or long_note.t1 == long_note.t2:
                continue
            if bpm < 0:
                bpm = -bpm
            judge_duration = 60000 / bpm / density_factor if bpm >= 255 else 30000 / bpm / density_factor
            count = int((end_time - start_time) / judge_duration)

            if count <= 1:
                result += 1
            elif long_note.has_head:
                result += count - 1
            else:
                result += count

        return result

    def get_total_combo(self) -> int:
        """Return the total combo of the chart."""
        combo_in_chart = sum([
            len(self.get_command_list_for_type(Tap)),  # Tap
            len(self.get_command_list_for_type(ArcTap)),  # ArcTap
            self.get_long_note_combo(self.get_command_list_for_type(Hold)),  # Hold
            self.get_long_note_combo(self._return_connected_arc_list()),  # Arc
        ])
        combo_in_timing_group = sum(
            control.get_total_combo()
            for control in self.command_list if isinstance(control, TimingGroup)
        )
        return combo_in_chart + combo_in_timing_group

    def get_interval(self) -> tuple[int, int]:
        """Return the interval (start and end time) of the chart."""
        return (
            min([_.get_interval()[0] for _ in self.command_list]),
            max([_.get_interval()[1] for _ in self.command_list]),
        )

    def get_bpm_proportion(self) -> dict[float, float]:
        """Return the proportion of BPMs in the chart. Ignore the bpm changes in timing group."""
        result: dict[float, Union[float, int]] = {}  # (BPM: Proportion)
        timing_list = self._sorted_timing_list
        timing_position_list = [_.t for _ in timing_list]
        timing_value_list = [_.bpm for _ in timing_list]
        duration = self.get_interval()[1]
        timing_position_list.append(duration)

        for index, bpm in enumerate(timing_value_list):
            if bpm not in result:
                result[bpm] = 0
            result[bpm] += (timing_position_list[index + 1] - timing_position_list[index]) / duration

        return result

    def get_sorted_timing_list(self) -> list['Timing']:
        """Return the sorted list of Timing."""
        return self._sorted_timing_list

    def get_duration(self) -> int:
        """Return the duration of the chart."""
        return self.get_interval()[1] - self.get_interval()[0]

    def syntax_check(self) -> bool:
        """Check the syntax of the chart as a whole."""
        raise NotImplementedError


class Note(Command, ABC):
    """Base class for all note types."""


class Tap(Note):
    """Ground tap."""

    def __init__(self, t: int, lane: int):
        self.t = t
        self.lane = lane

    def __repr__(self):
        return f'[{self.t} Tap] on lane {self.lane}'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t, int),
            self.lane in range(1, 5),
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t, self.t


class LongNote(Note, ABC):
    """Hold and Arc."""
    t1: int
    t2: int
    has_head = True


class Hold(LongNote):
    """Ground hold."""

    def __init__(
            self,
            t1: int, t2: int,
            lane: int
    ):
        self.t1 = t1
        self.t2 = t2
        self.lane = lane

    def __repr__(self):
        return f'[{self.t1} -> {self.t2} Hold] on lane {self.lane}'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t1, int),
            isinstance(self.t2, int),
            self.t1 < self.t2,
            self.lane in range(1, 5),
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t1, self.t2


class Arc(LongNote):
    """Arc."""

    def __init__(
            self,
            t1: int, t2: int,
            x1: float, x2: float,
            easing: str,
            y1: float, y2: float,
            color: int,
            FX: str,
            is_skyline: str,
            arctap_list: list[Optional['ArcTap']],
    ):
        self.t1 = t1
        self.t2 = t2
        self.x1 = x1
        self.x2 = x2
        self.easing = easing
        self.y1 = y1
        self.y2 = y2
        self.color = Color(color)
        self.FX = FX
        # Regardless of the value of is_skyline,
        # as long as arctap_list exists, then it must be skyline.
        self.is_skyline = {
                              AffToken.Value.SkyLine.true: True,
                              AffToken.Value.SkyLine.false: False
                          }[is_skyline] or bool(arctap_list)
        self.arctap_list = arctap_list

    def __repr__(self):
        pos = f'from ({self.x1}, {self.y1}) to ({self.x2}, {self.y2})'
        if self.is_skyline:
            if self.arctap_list:
                literal_arctap_list = ', with arctap: ' + ' '.join(map(lambda _: str(_.tn), self.arctap_list))
            else:
                literal_arctap_list = ''
            return (
                f'[{self.t1} -> {self.t2} Skyline] {self.has_head} {pos}'
                f'{literal_arctap_list}'
            )
        return f'[{self.t1} -> {self.t2} {self.color} Arc] {self.has_head} {pos}'

    def __eq__(self, other):
        return all([
            self.t1 == other.t1,
            self.t2 == other.t2,
            self.x1 == other.x1,
            self.x2 == other.x2,
            self.y1 == other.y1,
            self.y2 == other.y2,
        ])

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t1, int),
            isinstance(self.t2, int),
            any([
                self.t1 <= self.t2,
                self.t1 > self.t2 and self.is_skyline,
            ]),
            self.t1 >= 0,
            self.t2 >= 0,
            isinstance(self.x1, float),
            isinstance(self.x2, float),
            isinstance(self.y1, float),
            isinstance(self.y2, float),
            self.color != Color.Error,
            self.easing in AffToken.Value.Easing.all,
            self.FX in AffToken.Value.FX.all,
        ])

    def get_arctap_count(self) -> int:
        """Return the number of ArcTap note on this Arc."""
        return len(self.arctap_list)

    def get_interval(self) -> tuple[int, int]:
        return self.t1, self.t2


class ArcTap(Note):
    """Taps on skyline."""

    def __init__(
            self,
            tn: int,
            arc_timing_window: tuple[int, int],
            color: int
    ):
        self.tn = tn
        self.arc_timing_window = arc_timing_window  # (t1, t2) of the located arc
        self.color = Color(color)

    def __repr__(self):
        return f'[{self.tn} ArcTap] on Arc ({self.arc_timing_window}), {self.color})'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.tn, int),
            self.arc_timing_window[0] <= self.tn <= self.arc_timing_window[1],
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.tn, self.tn


class Flick(Note):
    """Flick. NEVER used in practice."""

    def __init__(
            self,
            t: int,
            x: float, y: float,
            vx: float, vy: float
    ):
        self.t = t
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy

    def __repr__(self):
        return f'[{self.t} Flick] at ({self.x}, {self.y}) with velocity ({self.vx}, {self.vy})'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t, int),
            isinstance(self.x, float),
            isinstance(self.y, float),
            isinstance(self.vx, float),
            isinstance(self.vy, float),
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t, self.t


class Control(Command, ABC):
    """Base class for control commands."""


class Timing(Control):
    """Change bpm and beats."""

    def __init__(
            self,
            t: int,
            bpm: float, beats: float,
            in_timing_group: bool = False
    ):
        self.t = t
        self.bpm = bpm
        self.beats = beats
        self.in_timing_group = in_timing_group

    def __repr__(self):
        return f'[{self.t} Timing] change bpm to {self.bpm} with {self.beats} beats'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t, int),
            isinstance(self.bpm, float),
            isinstance(self.beats, float),
            any([
                self.beats != 0,
                self.in_timing_group,
            ]),
            any([
                self.bpm >= 0,
                self.t != 0,
                self.in_timing_group,
            ])
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t, self.t


class Camera(Control):
    """Change camera position. Only works properly in the April Fool's version."""

    def __init__(
            self,
            t: int,
            transverse: float,
            bottom_zoom: float,
            line_zoom: float,
            steady_angle: float,
            top_zoom: float,
            angle: float,
            easing: str,
            lasting_time: int
    ):
        self.t = t
        self.transverse = transverse
        self.bottom_zoom = bottom_zoom
        self.line_zoom = line_zoom
        self.steady_angle = steady_angle
        self.top_zoom = top_zoom
        self.angle = angle
        self.easing = easing
        self.lasting_time = lasting_time

    def __repr__(self):
        return (
            f'[{self.t} Camera] zoom: ({self.transverse}, {self.bottom_zoom}, {self.line_zoom}), '
            f'angle: ({self.steady_angle}, {self.top_zoom}, {self.angle}), '
            f'lasting: {self.lasting_time}'
        )

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t, int),
            isinstance(self.transverse, float),
            isinstance(self.bottom_zoom, float),
            isinstance(self.line_zoom, float),
            isinstance(self.steady_angle, float),
            isinstance(self.top_zoom, float),
            isinstance(self.angle, float),
            self.easing in AffToken.Value.Camera.all,
            isinstance(self.lasting_time, int),
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t, self.t + self.lasting_time


class SceneControl(Control):
    """Control the performance effect."""

    def __init__(
            self,
            t: int,
            type_: str,
            param1: Optional[float] = None,
            param2: Optional[int] = None,
    ):
        self.t = t
        self.type_ = type_
        self.param1 = param1
        self.param2 = param2

    def __repr__(self):
        return f'[{self.t} SceneControl] type: {self.type_}'

    def syntax_check(self) -> bool:
        return all([
            isinstance(self.t, int),
            self.type_ in AffToken.Value.SceneControl.all,
            any([  # syntax check for specific scene control types
                all([
                    self.type_ in [
                        AffToken.Value.SceneControl.track_hide,
                        AffToken.Value.SceneControl.track_show,
                        AffToken.Value.SceneControl.arcahv_distort
                    ],
                    self.param1 is None,
                    self.param2 is None,
                ]),
                all([
                    self.type_ in [
                        AffToken.Value.SceneControl.track_display,
                        AffToken.Value.SceneControl.redline,
                        AffToken.Value.SceneControl.arcahv_debris
                    ],
                    isinstance(self.param1, float),
                    isinstance(self.param2, int),
                ]),
                all([
                    self.type_ == AffToken.Value.SceneControl.hide_group,
                    isinstance(self.param1, float),
                    self.param2 in range(2),
                ])
            ]),
        ])

    def get_interval(self) -> tuple[int, int]:
        return self.t, self.t


class TimingGroup(Chart, Control):
    """Use the internal independent timing statements to control Notes and Controls within the group."""

    def __init__(self, type_list: list[str], command_list: list[Command]):
        super().__init__({}, command_list)  # TimingGroup is a Chart without headers
        self.type_list = type_list

    def __repr__(self):
        literal_type = f', type: {" ".join(self.type_list)}' if self.type_list else ''
        return f'[TimingGroup] {len(self.command_list)} commands{literal_type}'

    def __str__(self):
        return self.__repr__() + '\n > ' + '\n > '.join([str(_) for _ in self.command_list])

    def syntax_check(self) -> bool:
        """Overrides Chart.syntax_check(), it just checks the inner commands."""
        return all([
            isinstance(self.type_list, list),
            all(sub_type in AffToken.Value.TimingGroup.all for sub_type in self.type_list),
            isinstance(self.command_list, list),
            all(sub_command.syntax_check() for sub_command in self.command_list)
        ])

    def get_total_combo(self) -> int:
        """
        Return the total combo in this timing group.
        Return 0 if 'type_list' contains 'noinput'.
        """
        return 0 if 'noinput' in self.type_list else super(TimingGroup, self).get_total_combo()

    def sub_command_syntax_check(self) -> list[tuple[Command, bool]]:
        """Check the syntax of each subcommand (Note and Control) within the group individually."""
        return [(sub_command, sub_command.syntax_check()) for sub_command in self.command_list]
