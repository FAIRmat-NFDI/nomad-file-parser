"""The mapper tree C (source `c`) → S (source `.s`) → E (path `.e`) and its sources."""

from copy import deepcopy
from typing import Any

from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Mapper, Path

from .paths import PathStr
from .support import SourceParser

JOINED = PathStr('c[*].s[*].e')

# SCF steps: with a leaf `e`, or without one.
steps = st.one_of(st.integers(-2, 2).map(lambda e: {'e': e}), st.just({'x': 0}))
# Calculations: steps (possibly none), or no `s` at all.
calculations = st.one_of(
    st.lists(steps, max_size=3).map(lambda s: {'s': s}), st.just({})
)
sources = st.lists(calculations, max_size=4).map(lambda c: {'c': c})
# Sources in which every calculation has at least one step with a leaf.
dense = st.lists(
    st.lists(st.integers(-2, 2), min_size=1, max_size=3), min_size=1, max_size=4
).map(lambda c: {'c': [{'s': [{'e': e} for e in s]} for s in c]})


def section(target: str, source: str, mappers: list, indices: list[int] | None):
    """The spec of a section mapper; `indices=None` leaves the key unset."""
    spec = dict(target=target, source=source, mapper=mappers)
    if indices is not None:
        spec['indices'] = indices
    return spec


def run_mapper(specs: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    """The result of the mapper built from `specs` on a copy of `source`."""
    source = deepcopy(source)
    mapper = Mapper.from_dict({'mapper': specs})
    return mapper.get_data(source, SourceParser(data=source))


def tree(source, outer: list[int] | None = [], inner: list[int] | None = []):
    """Run the mapper C → S → E on `source`, with `indices=outer` on C and `indices=inner` on S."""
    leaf = dict(target='E', path='.e')
    specs = [section('C', 'c', [section('S', '.s', [leaf], inner)], outer)]
    return run_mapper(specs, source)


def values(result: dict[str, Any]) -> list[list[Any]]:
    """The `E` values of a repeating `C` → repeating `S` result as nested lists."""
    return [[s['E'] for s in c['S']] for c in result.get('C', [])]


def per_element(source: dict[str, Any]) -> list[list[Any]]:
    """Path(s[*].e).get_data(c) for each calculation c by source position, `[]` where it fails."""
    return [Path(path='s[*].e').get_data(c) or [] for c in source['c']]


@st.composite
def indexed(draw):
    """A source with at least one calculation and a non-empty subset K of its positions."""
    source = draw(sources.filter(lambda x: x['c']))
    positions = st.integers(0, len(source['c']) - 1)
    return source, sorted(draw(st.sets(positions, min_size=1)))


TWO = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': [{'e': 3}]}]}
GAP = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': []}, {'s': [{'e': 3}]}]}
TREE_TWO = {'C': [{'S': [{'E': 1}, {'E': 2}]}, {'S': [{'E': 3}]}]}


def leaf_under(source: str) -> list[dict[str, Any]]:
    """One repeating section `S` with source `source` and the quantity `E` = `.e`."""
    return [section('S', source, [dict(target='E', path='.e')], [])]


@st.composite
def index_lists(draw):
    """A source with at least one calculation and a non-empty list K of integers.

    K is unordered, may repeat entries, and may hold negative or out-of-range
    positions (from -3 to len + 2).
    """
    source = draw(sources.filter(lambda x: x['c']))
    n = len(source['c'])
    return source, draw(st.lists(st.integers(-3, n + 2), min_size=1, max_size=5))
