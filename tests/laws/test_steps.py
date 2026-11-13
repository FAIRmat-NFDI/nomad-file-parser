"""Steps that `Path` implements itself: fields, indices and slices.

`Path` evaluates paths with a subclass of the JMESPath interpreter that
reimplements the field, index and slice steps (`visit_field`, `visit_index`,
`visit_slice` in `mapping_parser.py`). These laws check that the
reimplementation keeps the JMESPath meaning, and state where it deliberately
departs from it: a field on a list reads the last element (question 1).
Behaviour that runs JMESPath's own code (projections, pipe, filters, `@`) is
listed in `README.md` and not tested here.

The index step is split in two laws by its domain: `test_index_step` covers
every index except a negative one past the start of a list, which
`test_index_past_start_is_none` states separately as a strict xfail
(question 2). Together they state one rule: v[i] when -len(v) <= i < len(v),
else None.
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr, Slice
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
    """Path([i]).get_data(v) = v[i] when `v` is a list and -len(v) <= i < len(v), else None.

    For every `i` except a negative index past the start of a list
    (i < -len(v)), which is the next law.
    """
    assume(not (isinstance(node, list) and i < -len(node)))
    found = isinstance(node, list) and -len(node) <= i < len(node)
    expected = node[i] if found else None
    assert Path(path=f'[{i}]').get_data(node) == expected


@pytest.mark.question(2)
@pytest.mark.xfail(strict=True, reason='negative index past the start reads an element')
@given(st.lists(any_node, max_size=3), st.integers(1, 3))
def test_index_past_start_is_none(items, extra):
    """Path([i]).get_data(vs) = None for a list `vs` and i < -len(vs).

    Agreed (question 2). Fails today: `visit_index` guards only the positive
    side in search mode and pads the list, so Path([-3]).get_data([1, 2]) = 1
    (and the list becomes [1, 2, {}], see `test_get_does_not_mutate_source`).
    """
    i = -len(items) - extra
    assert Path(path=f'[{i}]').get_data(items) is None


bounds = st.none() | st.integers(-7, 7)
strides = st.sampled_from([None, 1, 2, 3, -1, -2])


@pytest.mark.question(3)
@given(st.lists(any_node, max_size=5), bounds, bounds, strides)
def test_slice_step(items, start, stop, stride):
    """Path(v[a:b:c]).get_data({v: vs}) = [x for x in vs[a:b:c] if x is not None].

    Agreed (question 3): a slice selects as Python and JMESPath do, so bounds
    beyond the ends are clamped and `[::3]` takes every third element; as a
    projection it drops `None` elements. Fails today: `visit_slice` gives
    None once a position of range(a or 0, b or len(vs), c or 1) is >= len(vs)
    or <= -len(vs).
    """
    path = f'v{Slice(start, stop, stride)}'
    expected = [x for x in items[slice(start, stop, stride)] if x is not None]
    assert Path(path=path).get_data({'v': items}) == expected


@given(any_node, bounds, bounds)
def test_slice_on_non_list_is_none(node, start, stop):
    """Path([a:b]).get_data(v) = None when `v` is not a list."""
    assume(not isinstance(node, list))
    assert Path(path=str(Slice(start, stop))).get_data(node) is None


TEN = {'v': list(range(10))}


@pytest.mark.question(3)
@pytest.mark.parametrize(
    'path, expected',
    [
        pytest.param('v[::3]', [0, 3, 6, 9], id='every-third'),
        pytest.param('v[1:8:3]', [1, 4, 7], id='every-third-inside'),
        pytest.param('v[0:10:3]', [0, 3, 6, 9], id='stop-at-end'),
        pytest.param('v[0:13:3]', [0, 3, 6, 9], id='stop-beyond-end'),
        pytest.param('v[-11:3]', [0, 1, 2], id='start-before-start'),
        pytest.param('v[-10:2]', [0, 1], id='start-at-minus-length'),
        pytest.param('v[8:]', [8, 9], id='to-the-end'),
        pytest.param('v[::-4]', [9, 5, 1], id='backwards'),
        pytest.param('v[12:]', [], id='start-beyond-end'),
    ],
)
def test_pinned_slices(path, expected):
    """Path(p).get_data({v: [0, …, 9]}) on hand-picked slices, with the agreed value per case."""
    assert Path(path=PathStr(path)).get_data(TEN) == expected


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
        pytest.param({'a': {'e': {}}}, 'a.e', {}, id='empty-object-is-a-value'),
    ],
)
def test_pinned_steps(obj, path, expected):
    """Path(p).get_data(obj) on field cases the generators do not produce, with the expected value per case.

    The field-on-list rule seen through a pipe and inside a filter
    condition, and an empty object as a stored value.
    """
    assert Path(path=PathStr(path)).get_data(obj) == expected
