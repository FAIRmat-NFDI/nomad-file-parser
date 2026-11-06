"""Paths as formatted strings, and the trees they are evaluated on."""

import re
from functools import cached_property
from typing import TypeAlias

from nomad_file_parser.mapping_parser import JmespathParser

# A stored `None` is a leaf; `None` is also the failure flag of `Path.get_data`, so a
# leaf holding `None` and a missing path read the same.
Leaf: TypeAlias = bool | int | float | str | None
Tree: TypeAlias = dict[str, 'Tree'] | list['Tree'] | Leaf

Step: TypeAlias = str | int  # a field name, an index, or PROJECT
PROJECT = '*'

STEP = re.compile(r'\.?(?:(?P<field>[A-Za-z_]\w*)|(?P<at>@)|\[(?P<index>\*|-?\d+)\])')


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

        A projection is opened by `[*]` and stays open up to the next `|`, so
        it is open at the end exactly when the last segment contains `[*]`.
        In JMESPath, slices, filters, `.*` and `[]` open one too; the laws
        generate none of them.
        """
        return PROJECT in self.segments[-1]

    def starts_with_field(self) -> bool:
        """Whether the first step is a field, so that `@.p` and `p0.p` are valid."""
        return bool(self.removeprefix('.')[:1].isalpha())

    @cached_property
    def segments(self) -> list[list[Step]]:
        """The steps of each segment, for the fragment of fields, indices, `[*]` and `@`.

        Raises `ValueError` for anything else (functions, slices, filters).
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
                text = text[match.end() :]
            segments.append(steps)
        return segments

    @classmethod
    def from_steps(cls, *segments: list[Step]) -> 'PathStr':
        """The path of the given segments, joined by `|`."""
        return cls(' | '.join(render(steps) for steps in segments))


def render(steps: list[Step]) -> str:
    """One segment as text: fields joined by `.`, `[i]` and `[*]` attached."""
    out = ''
    for step in steps:
        if step == PROJECT:
            out += '[*]'
        elif isinstance(step, int):
            out += f'[{step}]'
        else:
            out += f'.{step}' if out else step
    return out
