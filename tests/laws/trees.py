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


def section(target: str, source: str, mappers: list, *, repeats: bool) -> dict[str, Any]:
    """The spec of a section mapper."""
    return dict(target=target, source=source, mapper=mappers, repeats=repeats)


def run_mapper(specs: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    """The result of the mapper built from `specs` on a copy of `source`."""
    source = deepcopy(source)
    mapper = Mapper.from_dict({'mapper': specs})
    return mapper.get_data(source, SourceParser(data=source))


def tree(source: dict[str, Any], *,
        outer_repeats: bool = True, inner_repeats: bool = True) -> dict[str, Any]:
    """Run the mapper C → S → E on `source`."""
    leaf = dict(target='E', path='.e')
    specs_inner = section('S', '.s', [leaf], repeats=inner_repeats)
    specs = [section('C', 'c', [specs_inner], repeats=outer_repeats)]
    return run_mapper(specs, source)


def values(result: dict[str, Any]) -> list[list[Any]]:
    """The `E` values of a repeating `C` → repeating `S` result as nested lists."""
    return [[s['E'] for s in c['S']] for c in result.get('C', [])]


def per_element(source: dict[str, Any]) -> list[list[Any]]:
    """Path(s[*].e).get_data(c) for each calculation c by source position, `[]` where it fails."""
    return [Path(path='s[*].e').get_data(c) or [] for c in source['c']]


TWO = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': [{'e': 3}]}]}
GAP = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': []}, {'s': [{'e': 3}]}]}
TREE_TWO = {'C': [{'S': [{'E': 1}, {'E': 2}]}, {'S': [{'E': 3}]}]}


def leaf_under(source: str) -> list[dict[str, Any]]:
    """One repeating section `S` with source `source` and the quantity `E` = `.e`."""
    return [section('S', source, [dict(target='E', path='.e')], repeats=True)]
