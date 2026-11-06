"""Filters: `[?k==v]` selects list elements and, like `[*]`, opens a projection.

The parsers use filters to pick an element by an attribute, then close the
projection with `|` to take the first match (`vasp.py`:
`.i[?"@name"=='program'] | [0].__value`). Without the pipe, the index would
be applied to each match.
"""

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import Filter, Leaf, PathStr
from .strategies import at_filter, keys, leaves, nodes

any_node = st.one_of(nodes(0), nodes(1), nodes(2))


def same(a: Leaf | None, b: Leaf) -> bool:
    """Equality as the filter compares: by type and value, so `1` is not `true`."""
    return type(a) is type(b) and a == b


@pytest.mark.question(1)
@given(st.lists(any_node, max_size=4), keys, leaves)
def test_filter_step(items, k, v):
    """Path(vs[?k==v]).get_data(obj) = [o for o in vs if o is not None and same(Path(k).get_data(o), v)].

    The condition reads `k` with the field rules of `Path`: a missing key
    reads `None` and so matches `null`, and a field on a list element reads
    its last element (question 1). A `None` element is dropped.
    """
    expected = [o for o in items if o is not None and same(Path(path=k).get_data(o), v)]
    assert Path(path=f'v{Filter(k, v)}').get_data({'v': items}) == expected


@given(any_node, keys, leaves)
def test_filter_on_non_list_is_none(node, k, v):
    """Path([?k==v]).get_data(v) = None when `v` is not a list."""
    assume(not isinstance(node, list))
    assert Path(path=str(Filter(k, v))).get_data(node) is None


@given(at_filter())
def test_dot_maps_under_filter(case):
    """Path(p0[?f].q).get_data(obj) = [r for o in Path(p0[?f]).get_data(obj) if (r := Path(q).get_data(o)) is not None].

    When `p0` opens no projection: after a filter the dot applies `q` to
    each selected element, as after `[*]`.
    """
    obj, p0, condition, rest = case
    assume(rest)
    selected, q = p0.dot(str(condition)), PathStr.from_steps(rest)
    assert not p0.opens_projection()  # ensured by the generator
    base = Path(path=selected).get_data(obj)
    mapped = None
    if isinstance(base, list):
        mapped = [r for o in base if (r := Path(path=q).get_data(o)) is not None]
    assert Path(path=selected.dot(q)).get_data(obj) == mapped


@given(at_filter())
def test_pipe_closes_filter(case):
    """Path(p0[?f] | q).get_data(obj) = Path(q).get_data(Path(p0[?f]).get_data(obj)).

    The pipe hands the whole list of matches to `q`, so `| [0]` takes the
    first match.
    """
    obj, p0, condition, rest = case
    assume(rest)
    selected, q = p0.dot(str(condition)), PathStr.from_steps(rest)
    assert Path(path=selected | q).get_data(obj) == Path(path=q).get_data(
        Path(path=selected).get_data(obj)
    )


# The shape `XMLParser` gives repeated elements with attributes, as in `vasprun.xml`.
ITEMS = {
    'i': [
        {'@name': 'program', '__value': 'VASP'},
        {'@name': 'version', '__value': '6.4'},
        {'@name': 'program', '__value': 'other'},
    ]
}
PROGRAM = """i[?"@name"=='program']"""
VASP, OTHER = ITEMS['i'][0], ITEMS['i'][2]


@pytest.mark.parametrize(
    'obj, path, expected',
    [
        pytest.param(ITEMS, PROGRAM, [VASP, OTHER], id='filter-selects'),
        pytest.param(ITEMS, f'{PROGRAM}[0]', [], id='index-per-match'),
        pytest.param(ITEMS, f'{PROGRAM} | [0]', VASP, id='pipe-takes-first-match'),
        pytest.param(ITEMS, f'{PROGRAM}.__value', ['VASP', 'other'], id='dot-maps'),
        pytest.param(ITEMS, f'{PROGRAM} | [0].__value', 'VASP', id='vasp-program'),
        pytest.param(ITEMS, f'{PROGRAM}.__value | [0]', 'VASP', id='close-later'),
        pytest.param(ITEMS, f'{PROGRAM}[0].__value', [], id='no-pipe-reads-nothing'),
        pytest.param(
            ITEMS, """i[?"@name"=='none'] | [0]""", None, id='no-match-first-is-none'
        ),
        pytest.param(
            {'v': [{'a': 1}, {'a': True}]},
            'v[?a==`1`]',
            [{'a': 1}],
            id='typed-equality',
        ),
        pytest.param(
            {'v': [{'a': None}, {}]},
            'v[?a==`null`]',
            [{'a': None}, {}],
            id='missing-matches-null',
        ),
        pytest.param({'v': [None]}, 'v[?a==`null`]', [], id='none-element-dropped'),
        pytest.param(
            {'v': [[{'a': 1}]]},
            'v[?a==`1`]',
            [[{'a': 1}]],
            id='field-on-list-in-condition',
            marks=pytest.mark.question(1),
        ),
        pytest.param({'v': {'a': 1}}, 'v[?a==`1`]', None, id='filter-on-object'),
    ],
)
def test_pinned_filters(obj, path, expected):
    """Path(p).get_data(obj) on hand-picked filter cases, with the expected value per case."""
    assert Path(path=PathStr(path)).get_data(obj) == expected
