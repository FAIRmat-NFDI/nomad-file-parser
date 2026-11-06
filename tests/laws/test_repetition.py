"""Repetition: sections built from lists by nested mappers, and `indices`.

`tree(obj, outer=K, inner=L)` runs the mapper `C` (source `c`, `indices=K`) →
`S` (source `.s`, `indices=L`) → `E` (path `.e`) on `obj` with
`Mapper.get_data` (`trees.py`); both default to `[]`, which requests every
element as a list, and `None` requests a single value. `values(result)` reads
the `E` values of a result as nested lists.
"""

import pytest
from hypothesis import example, given

from nomad_file_parser.mapping_parser import Path

from .trees import (
    GAP,
    JOINED,
    TREE_TWO,
    TWO,
    dense,
    indexed,
    leaf_under,
    per_element,
    run_mapper,
    sources,
    tree,
    values,
)


@given(dense)
def test_nested_sections_follow_joined_path(source):
    """values(tree(obj)) = Path(c[*].s[*].e).get_data(obj) when every calculation has a step with `e`.

    Nesting repeating sections composes like `.` in a path: one list level
    per section.
    """
    assert values(tree(source)) == Path(path=JOINED).get_data(source)


@pytest.mark.question(8, 9)
@given(sources)
@example({'c': [{'s': [{'e': 1}]}, {'s': []}, {}]})  # empty and missing `s`
@example({'c': []})
def test_nested_sections_drop_empty(source):
    """values(tree(obj)) = [l for l in Path(c[*].s[*].e).get_data(obj) if l != []].

    The path drops only `None` (missing `s`) and keeps `[]` for a
    calculation without leaves; the mapper drops both (questions 8, 9).
    """
    expected = [inner for inner in Path(path=JOINED).get_data(source) if inner]
    assert values(tree(source)) == expected


@pytest.mark.question(7)
@given(sources)
def test_unindexed_outer_takes_first(source):
    """tree(obj, outer=None) = {C: tree(obj)[C][0]}, or {} when tree(obj) has no `C`.

    Without `indices`, a section keeps only the first non-empty element of a
    list source (question 7); `{}` when there is none.
    """
    repeats = tree(source).get('C', [])
    expected = {'C': repeats[0]} if repeats else {}
    assert tree(source, outer=None) == expected


@pytest.mark.question(7)
@given(sources)
def test_unindexed_inner_takes_first(source):
    """tree(obj, inner=None)[C] = [{S: {E: l[0]}} for l in values(tree(obj))].

    The same rule one level down: each calculation keeps its first step with
    a leaf, not a list of them.
    """
    expected = [{'S': {'E': inner[0]}} for inner in values(tree(source))]
    assert tree(source, inner=None).get('C', []) == expected


@given(indexed())
def test_indices_are_source_positions(case):
    """values(tree(obj, outer=K)) = [l for n, l in enumerate(per_element(obj)) if n in K and l != []].

    With per_element(obj)[n] = Path(s[*].e).get_data(obj[c][n]), or [] where
    that is None.

    `indices` select by position in the source, before empty elements are
    dropped, so they do not count positions of the output.
    """
    source, positions = case
    expected = [
        inner for n, inner in enumerate(per_element(source)) if n in positions and inner
    ]
    assert values(tree(source, outer=positions)) == expected


@pytest.mark.parametrize(
    'specs, source, expected',
    [
        pytest.param(
            None,
            GAP,
            {'C': [{'S': [{'E': 1}, {'E': 2}]}, {'S': [{'E': 3}]}]},
            id='missing-vs-empty',
            marks=pytest.mark.question(8, 9),
        ),
        pytest.param(
            leaf_under('c[*].s[*]'),
            TWO,
            {'S': [{'E': 1}, {'E': 3}]},
            id='source-double-projection',
            marks=pytest.mark.question(10),
        ),
        pytest.param(
            leaf_under('c[*].s'),
            TWO,
            {'S': [{'E': 1}, {'E': 3}]},
            id='source-projection-of-lists',
            marks=pytest.mark.question(10),
        ),
        pytest.param(
            [1, 0],
            TWO,
            TREE_TWO,
            id='indices-order-ignored',
            marks=pytest.mark.question(11),
        ),
        pytest.param(
            [0, 0],
            TWO,
            {'C': [{'S': [{'E': 1}, {'E': 2}]}]},
            id='indices-duplicate',
            marks=pytest.mark.question(11),
        ),
        pytest.param(
            [-1], TWO, {}, id='indices-negative', marks=pytest.mark.question(12)
        ),
        pytest.param(
            [5], TWO, {}, id='indices-out-of-range', marks=pytest.mark.question(12)
        ),
        pytest.param(
            [1], GAP, {}, id='indices-select-empty', marks=pytest.mark.question(8)
        ),
    ],
)
def test_mapper_pinned(specs, source, expected):
    """Current behaviour asked about in `OPEN_QUESTIONS.md` (questions 8 to 12, per case).

    `specs` is `None` for tree(obj), a list of indices K for
    tree(obj, outer=K), or a full mapper spec for run_mapper(specs, obj). For `missing-vs-empty`, Path(c[*].s[*].e).get_data(obj) keeps the
    middle `[]` that the mapper drops.
    """
    if specs is None:
        assert Path(path=JOINED).get_data(source) == [[1, 2], [], [3]]
        result = tree(source)
    elif all(isinstance(i, int) for i in specs):
        result = tree(source, outer=specs)
    else:
        result = run_mapper(specs, source)
    assert result == expected
