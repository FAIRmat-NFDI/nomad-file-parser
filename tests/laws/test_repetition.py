"""Repetition: sections built from lists by nested mappers, and `indices`.

M_K,L(x) is the result of the tree C → S → E (`trees.py`) with `indices=K` on
`C` and `indices=L` on `S`, where `[]` requests every element as a list and
`None` a single value; values(…) reads the `E` values as nested lists.
"""

import pytest
from hypothesis import example, given

from .reference import get
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
    """values(M_[],[](x)) = eval(c[*].s[*].e)(x) when every element has a leaf.

    Nesting repeating sections composes like `.` in a path: one list level
    per section.
    """
    assert values(tree(source)) == get(JOINED, source)


@pytest.mark.question(8, 9)
@given(sources)
@example({'c': [{'s': [{'e': 1}]}, {'s': []}, {}]})  # empty and missing `s`
@example({'c': []})
def test_nested_sections_drop_empty(source):
    """values(M_[],[](x)) = [l for l in eval(c[*].s[*].e)(x) if l != []].

    The path drops only `None` (missing `s`) and keeps `[]` for a
    calculation without leaves; the mapper drops both (questions 8, 9).
    """
    expected = [inner for inner in get(JOINED, source) if inner]
    assert values(tree(source)) == expected


@pytest.mark.question(7)
@given(sources)
def test_unindexed_outer_takes_first(source):
    """M_None,[](x) = {C: c1} for the first non-empty repeat c1 of M_[],[](x).

    Without `indices`, a section keeps only the first non-empty element of a
    list source (question 7); `{}` when there is none.
    """
    repeats = tree(source).get('C', [])
    expected = {'C': repeats[0]} if repeats else {}
    assert tree(source, outer=None) == expected


@pytest.mark.question(7)
@given(sources)
def test_unindexed_inner_takes_first(source):
    """M_[],None(x)[C][i] = {S: {E: l[0]}} for each non-empty l in values(M_[],[](x)).

    The same rule one level down: each calculation keeps its first step with
    a leaf, not a list of them.
    """
    expected = [{'S': {'E': inner[0]}} for inner in values(tree(source))]
    assert tree(source, inner=None).get('C', []) == expected


@given(indexed())
def test_indices_are_source_positions(case):
    """values(M_K,[](x)) = [l_n for n in K if l_n != []], l_n = eval(s[*].e)(c_n).

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

    `specs` is either the `indices` of `C` in M_K,[] or a full mapper spec;
    `None` means M_[],[]. For `missing-vs-empty`, eval(c[*].s[*].e) keeps the
    middle `[]` that the mapper drops.
    """
    if specs is None:
        assert get(JOINED, source) == [[1, 2], [], [3]]
        result = tree(source)
    elif all(isinstance(i, int) for i in specs):
        result = tree(source, outer=specs)
    else:
        result = run_mapper(specs, source)
    assert result == expected
