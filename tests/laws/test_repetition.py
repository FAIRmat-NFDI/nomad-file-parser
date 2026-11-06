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
    JOINED,
    TWO,
    dense,
    index_lists,
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


@pytest.mark.question(11)
@given(index_lists())
@example((TWO, [1, 0]))
@example((TWO, [0, 0]))
def test_indices_order_and_duplicates_ignored(case):
    """values(tree(obj, outer=K)) = values(tree(obj, outer=sorted(set(K)))) for K within the positions of `c`.

    `indices` act as a set: their order and repetitions do not change the
    result, which keeps source order.
    """
    source, positions = case
    n = len(source['c'])
    positions = [k for k in positions if 0 <= k < n] or [0]
    assert values(tree(source, outer=positions)) == values(
        tree(source, outer=sorted(set(positions)))
    )


@pytest.mark.question(12)
@given(index_lists())
@example((TWO, [-1]))
@example((TWO, [5]))
def test_indices_outside_positions_select_nothing(case):
    """values(tree(obj, outer=K)) = values(tree(obj, outer=[k for k in K if 0 <= k < len(c)])), and [] when none is in range.

    Negative entries do not count from the end, unlike the path step `[-1]`,
    and out-of-range entries are ignored without a warning.
    """
    source, positions = case
    n = len(source['c'])
    in_range = [k for k in positions if 0 <= k < n]
    expected = values(tree(source, outer=in_range)) if in_range else []
    assert values(tree(source, outer=positions)) == expected


@pytest.mark.question(10)
@pytest.mark.parametrize('outer', ['c[*].s', 'c[*].s[*]'])
@given(sources)
@example(TWO)
def test_single_mapper_over_two_levels_takes_first(outer, source):
    """run_mapper(S from outer → E from .e, obj)[S] = [{E: l[0]} for l in per_element(obj) if l != []].

    One repeating mapper whose source crosses two list levels gives one
    section per calculation with a step that has `e`, holding the first such
    value, for `outer` = `c[*].s` and `c[*].s[*]` alike.
    """
    expected = [{'E': inner[0]} for inner in per_element(source) if inner]
    result = run_mapper(leaf_under(outer), source)
    assert result.get('S', []) == expected
