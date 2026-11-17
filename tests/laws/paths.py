"""Paths as formatted strings, and the trees they are evaluated on."""

import json
import re
from functools import cached_property
from typing import NamedTuple, TypeAlias

from nomad_file_parser.mapping_parser import JmespathParser

# A stored `None` is a leaf; `None` is also the failure flag of `Path.get_data`, so a
# leaf holding `None` and a missing path read the same.
Leaf: TypeAlias = bool | int | float | str | None
Tree: TypeAlias = dict[str, 'Tree'] | list['Tree'] | Leaf


class Filter(NamedTuple):
    """The filter step `[?key==`value`]`, which opens a projection like `[*]`."""

    key: str
    value: Leaf

    def __str__(self) -> str:
        return f'[?{self.key}==`{json.dumps(self.value)}`]'


class Slice(NamedTuple):
    """The slice step `[start:stop:step]`, which opens a projection like `[*]`."""

    start: int | None
    stop: int | None
    step: int | None = None

    def __str__(self) -> str:
        start, stop = ('' if x is None else str(x) for x in (self.start, self.stop))
        tail = '' if self.step is None else f':{self.step}'
        return f'[{start}:{stop}{tail}]'


Step: TypeAlias = (
    str | int | Filter | Slice
)  # a field, an index, PROJECT, a filter or a slice
PROJECT = '*'

STEP = re.compile(
    r'\.?(?:(?P<field>[A-Za-z_]\w*)|(?P<at>@)|\[(?P<index>\*|-?\d+)\]'
    r'|\[\?(?P<key>[A-Za-z_]\w*)==`(?P<value>[^`]*)`\]'
    r'|\[(?P<start>-?\d*):(?P<stop>-?\d*)(?::(?P<step>-?\d+))?\])'
)


class PathStr(str):
    """A path that parses: segments joined by `|`, each one steps joined by `.`.

    A leading `.` marks the path as relative to a parent. The format is
    checked on construction with the parser `Path` uses, so a malformed path
    raises here instead of reading as `None` later. Index and projection
    steps attach without a dot (`p[0]`, `p[*]`).
    """

    def __new__(cls, text: str) -> 'PathStr':
        JmespathParser().parse(text.removeprefix('.'))
        return super().__new__(cls, text)

    def __or__(self, other: str) -> 'PathStr':
        """p | q: the pipe, which hands the whole result of `p` to `q`."""
        return PathStr(f'{self} | {other}')

    def dot(self, other: str) -> 'PathStr':
        """p.q: the dot, which continues the segment (and an open projection)."""
        sep = '' if other.startswith('[') else '.'
        return PathStr(f'{self}{sep}{other}')

    def relative(self) -> 'PathStr':
        """.p: the same path, relative to a parent."""
        return PathStr(f'.{self}')

    def opens_projection(self) -> bool:
        """Whether a projection is still open at the end of the path.

        A projection is opened by `[*]`, a filter or a slice and stays open up
        to the next `|`, so it is open at the end exactly when the last segment
        contains one of them. In JMESPath, `.*` and `[]` open one too;
        the laws generate none of them.
        """
        return any(opens(step) for step in self.segments[-1])

    def starts_with_field(self) -> bool:
        """Whether the first step is a field, so that `@.p` and `p0.p` are valid."""
        return bool(self.removeprefix('.')[:1].isalpha())

    @cached_property
    def segments(self) -> list[list[Step]]:
        """The steps of each segment, for the fragment of fields, indices, `[*]`, filters and `@`.

        Raises `ValueError` for anything else (functions, slices, other conditions).
        """
        segments = []
        for text in self.removeprefix('.').split('|'):
            text, steps = text.strip(), []
            while text:
                match = STEP.match(text)
                if match is None:
                    raise ValueError(f'not in the fragment of the laws: {self!r}')
                if match['field']:
                    steps.append(match['field'])
                elif match['index'] == PROJECT:
                    steps.append(PROJECT)
                elif match['index']:
                    steps.append(int(match['index']))
                elif match['key']:
                    steps.append(Filter(match['key'], json.loads(match['value'])))
                elif match['start'] is not None:
                    bounds = [match[g] for g in ('start', 'stop', 'step')]
                    steps.append(Slice(*(int(b) if b else None for b in bounds)))
                text = text[match.end() :]
            segments.append(steps)
        return segments

    @classmethod
    def from_steps(cls, *segments: list[Step]) -> 'PathStr':
        """The path of the given segments, joined by `|`."""
        return cls(' | '.join(render(steps) for steps in segments))


def opens(step: Step) -> bool:
    """Whether `step` opens a projection: `[*]`, a filter or a slice."""
    return step == PROJECT or isinstance(step, Filter | Slice)


def render(steps: list[Step]) -> str:
    """One segment as text: fields joined by `.`, `[i]` and `[*]` attached."""
    out = ''
    for step in steps:
        if step == PROJECT:
            out += '[*]'
        elif isinstance(step, Filter | Slice):
            out += str(step)
        elif isinstance(step, int):
            out += f'[{step}]'
        else:
            out += f'.{step}' if out else step
    return out
