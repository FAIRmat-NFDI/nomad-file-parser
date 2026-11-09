"""Repetition: sections built from lists by nested mappers, and `indices`.

`tree(obj, outer=K, inner=L)` runs the mapper `C` (source `c`, `indices=K`) →
`S` (source `.s`, `indices=L`) → `E` (path `.e`) on `obj` with
`Mapper.get_data` (`trees.py`); both default to `[]`, which requests every
element as a list, and `None` requests a single value. `values(result)` reads
the `E` values of a result as nested lists. `per_element(obj)[n]` is
Path(s[*].e).get_data(obj[c][n]), or [] where that is None.
"""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

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


@given(st.one_of(dense, sources))
@example({'c': [{'s': [{'e': 1}]}, {'s': []}, {}]})  # empty and missing `s`
@example({'c': []})
def test_nested_sections_follow_joined_path(source):
    """values(tree(obj)) = [l for l in Path(c[*].s[*].e).get_data(obj) if l != []].

    Nesting repeating sections composes like `.` in a path, one list level
    per section, except that a calculation without leaves is dropped: the
    path keeps `[]` for it and drops only `None` (missing `s`), the mapper
    drops both, without a record (question 8, answered; question 9, closed).
    When every calculation has a step with `e`, both sides are the joined
    path itself.
    """
    expected = [inner for inner in Path(path=JOINED).get_data(source) if inner]
    assert values(tree(source)) == expected


@given(sources)
def test_unindexed_outer_takes_first(source):
    """tree(obj, outer=None) = {C: tree(obj)[C][0]}, or {} when tree(obj) has no `C`.

    A non-repeating section fed a list keeps its first non-empty element and
    drops the others (question 7, confirmed as intended); `{}` when there is
    none.
    """
    repeats = tree(source).get('C', [])
    expected = {'C': repeats[0]} if repeats else {}
    assert tree(source, outer=None) == expected


@given(sources)
def test_unindexed_inner_takes_first(source):
    """tree(obj, inner=None)[C] = [{S: {E: l[0]}} for l in values(tree(obj))].

    The same rule one level down: each calculation keeps its first step with
    a leaf, not a list of them (question 7).
    """
    expected = [{'S': {'E': inner[0]}} for inner in values(tree(source))]
    assert tree(source, inner=None).get('C', []) == expected


def unwrap(source: dict) -> dict:
    """`source` with every one-element list of calculations or steps replaced by its element."""
    calculations = [
        {**c, 's': c['s'][0]}
        if isinstance(c.get('s'), list) and len(c['s']) == 1
        else c
        for c in source['c']
    ]
    return {'c': calculations[0] if len(calculations) == 1 else calculations}


@given(sources)
@example({'c': [{'s': [{'e': 1}, {'e': 2}]}]})
def test_repeating_section_reads_a_dict_as_one_element(source):
    """tree(unwrap(obj)) = tree(obj): a repeating section fed a dict builds a list of one section.

    The converse of question 7: a repeating subsection whose source is a
    single object, not a list, is read as a list of that object, at either
    level.
    """
    assert tree(unwrap(source)) == tree(source)


@given(indexed())
def test_indices_are_source_positions(case):
    """values(tree(obj, outer=K)) = [l for n, l in enumerate(per_element(obj)) if n in K and l != []].

    For a sorted `K` without repeats. `indices` select by position in the
    source first, and only then are empty elements dropped: a position in
    `K` counts the input, not the output (question 8, answered).
    """
    source, positions = case
    expected = [
        inner for n, inner in enumerate(per_element(source)) if n in positions and inner
    ]
    assert values(tree(source, outer=positions)) == expected


@pytest.mark.question(11)
@pytest.mark.xfail(strict=True, reason='indices ignore their order and repeats')
@given(index_lists())
@example((TWO, [1, 0]))
@example((TWO, [0, 0]))
def test_indices_keep_order_and_repeats(case):
    """values(tree(obj, outer=K)) = [per_element(obj)[k] for k in K if per_element(obj)[k] != []], for 0 <= k < len(c).

    Agreed (question 11): `indices` select like a JMESPath multi-select
    `[c[k1], c[k2], …]`, in the order given and with repeats. Fails today:
    they act as a set, so the result keeps source order and a repeated
    position appears once.
    """
    source, positions = case
    n = len(source['c'])
    positions = [k for k in positions if 0 <= k < n] or [0]
    selected = per_element(source)
    expected = [selected[k] for k in positions if selected[k]]
    assert values(tree(source, outer=positions)) == expected


@pytest.mark.question(12)
@pytest.mark.xfail(strict=True, reason='negative indices select nothing')
@given(index_lists())
@example((TWO, [-1]))
def test_negative_indices_count_from_the_end(case):
    """values(tree(obj, outer=K)) = [per_element(obj)[k] for k in K if per_element(obj)[k] != []], for -len(c) <= k < len(c).

    Agreed (question 12): a negative entry selects position len(c) + k, as
    the path step `[k]` does. Out-of-range entries stay ignored. Fails today:
    a negative entry selects nothing.
    """
    source, positions = case
    n = len(source['c'])
    positions = [k for k in positions if -n <= k < n] or [-1]
    selected = per_element(source)
    expected = [selected[k] for k in positions if selected[k]]
    assert values(tree(source, outer=positions)) == expected


@pytest.mark.question(10)
@pytest.mark.parametrize('outer', ['c[*].s', 'c[*].s[*]'])
@given(sources)
@example(TWO)
def test_single_mapper_over_two_levels_takes_first(outer, source):
    """run_mapper(S from outer → E from .e, obj)[S] = [{E: l[0]} for l in per_element(obj) if l != []].

    Today's behaviour: one repeating mapper whose source crosses two list
    levels gives one section per calculation with a step that has `e`,
    holding the first such value, for `outer` = `c[*].s` and `c[*].s[*]`
    alike. Question 10 records the two positions on whether the nesting
    depth should be set by the schema rather than by the data.
    """
    expected = [{'E': inner[0]} for inner in per_element(source) if inner]
    result = run_mapper(leaf_under(outer), source)
    assert result.get('S', []) == expected
