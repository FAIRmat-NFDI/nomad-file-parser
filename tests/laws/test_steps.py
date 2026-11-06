"""Steps that `Path` implements itself: fields and indices.

`Path` evaluates paths with a subclass of the JMESPath interpreter that
reimplements the field and the index step (`visit_field`, `visit_index` in
`mapping_parser.py`). These laws check that the reimplementation keeps the
JMESPath meaning, and state where it deliberately departs from it: a field
on a list reads the last element (question 1). Behaviour that runs
JMESPath's own code (projections, pipe, filters, `@`) is listed in
`README.md` and not tested here.
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr
from .strategies import keys, nodes

# Single steps are applied to nodes of any shape: objects, lists, leaves.
any_node = st.one_of(nodes(0), nodes(1), nodes(2))


@given(any_node, keys)
def test_field_step(node, k):
    """Path(k).get_data(v) = v[k] when `v` is an object holding `k`, else None.

    Lists are excluded here; a field on a list is the next law.
    """
    assume(not isinstance(node, list))
    expected = node.get(k) if isinstance(node, dict) else None
    assert Path(path=k).get_data(node) == expected


@pytest.mark.question(1)
@given(st.lists(any_node, max_size=3), keys)
def test_field_on_list_reads_last(items, k):
    """Path(v.k).get_data({v: vs}) = Path(k).get_data(vs[-1]) for a non-empty list `vs`, None for [].

    One level only: if the last element is itself a list, the field gives
    None. The list sits under `v` because a top-level list is not reached
    through a field. JMESPath gives None for any field on a list.
    """
    last = items[-1] if items else None
    expected = last.get(k) if isinstance(last, dict) else None
    assert Path(path=f'v.{k}').get_data({'v': items}) == expected


@given(any_node, st.integers(-3, 3))
def test_index_step(node, i):
    """Path([i]).get_data(v) = v[i] when `v` is a list and -len(v) ≤ i < len(v), else None.

    Negative indices past the start are left to `test_get_does_not_mutate_source`.
    """
    assume(not (isinstance(node, list) and i < -len(node)))
    found = isinstance(node, list) and -len(node) <= i < len(node)
    expected = node[i] if found else None
    assert Path(path=f'[{i}]').get_data(node) == expected


# A list of objects in which one element lacks the field `x`.
LISTS = {'a': [{'x': {'y': 1}}, {}, {'x': {'y': 2}}]}
FIELD_ON_LIST = pytest.mark.question(1)


@pytest.mark.parametrize(
    'obj, path, expected',
    [
        pytest.param(LISTS, 'a.x', {'y': 2}, id='field-on-list', marks=FIELD_ON_LIST),
        pytest.param(
            LISTS,
            'a[*] | x',
            {'y': 2},
            id='field-after-closed-projection',
            marks=FIELD_ON_LIST,
        ),
        pytest.param(
            {'v': [[{'a': 1}]]},
            'v[?a==`1`]',
            [[{'a': 1}]],
            id='field-on-list-in-filter-condition',
            marks=FIELD_ON_LIST,
        ),
        pytest.param({'a': []}, 'a.x', None, id='field-on-empty-list'),
        pytest.param({'a': [1, 2]}, 'a.x', None, id='field-on-list-of-scalars'),
        pytest.param({'a': {}}, 'a.x', None, id='missing'),
        pytest.param({'a': {'n': None}}, 'a.n', None, id='holds-none-like-missing'),
        pytest.param({'a': {'b': 0}}, 'a.b.c', None, id='into-leaf-like-missing'),
        pytest.param({'a': {'e': {}}}, 'a.e', {}, id='empty-object-is-a-value'),
        pytest.param({'a': {'z': 0}}, 'a.z', 0, id='zero-is-a-value'),
        pytest.param({'a': {'f': False}}, 'a.f', False, id='false-is-a-value'),
        pytest.param({'a': {'s': ''}}, 'a.s', '', id='empty-string-is-a-value'),
        pytest.param(LISTS, 'a[*].x[0]', [], id='index-on-objects-per-element'),
        pytest.param({'a': [1, 2]}, 'a[-1]', 2, id='negative-from-end'),
        pytest.param({'a': [1, 2]}, 'a[-2]', 1, id='negative-first'),
        pytest.param(LISTS, 'a[*].x.y | [-1]', 2, id='negative-after-pipe'),
        pytest.param(
            {'a': [[1, 2], [3]]}, 'a[*][-1]', [2, 3], id='negative-per-element'
        ),
    ],
)
def test_pinned_steps(obj, path, expected):
    """Path(p).get_data(obj) on hand-picked field and index cases, with the expected value per case."""
    assert Path(path=PathStr(path)).get_data(obj) == expected
