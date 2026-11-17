"""Repetition: sections built from lists by nested mappers.

`tree(obj, outer_repeats=True, inner_repeats=True)` runs the mapper
`C` (source `c`) → `S` (source `.s`) → `E` (path `.e`) on `obj`
with `Mapper.get_data` (`trees.py`). `{outer,inner}_repeats=True`
requests every element as a list, and `False` requests a single value.
`values(result)` reads the `E` values of a result as nested lists.
`per_element(obj)[n]` is Path(s[*].e).get_data(obj[c][n]), or [] where that is None.
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
    """tree(obj, outer_repeats=False) = {C: tree(obj)[C][0]}, or {} when tree(obj) has no `C`.

    A non-repeating section fed a list keeps its first non-empty element and
    drops the others (question 7, confirmed as intended); `{}` when there is
    none.
    """
    repeats = tree(source).get('C', [])
    expected = {'C': repeats[0]} if repeats else {}
    assert tree(source, outer_repeats=False) == expected


@given(sources)
def test_unindexed_inner_takes_first(source):
    """tree(obj, inner_repeats=False)[C] = [{S: {E: l[0]}} for l in values(tree(obj))].

    The same rule one level down: each calculation keeps its first step with
    a leaf, not a list of them (question 7).
    """
    expected = [{'S': {'E': inner[0]}} for inner in values(tree(source))]
    assert tree(source, inner_repeats=False).get('C', []) == expected


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
