"""Traversal: what one step does, and how steps compose.

The step laws fix a field, an index and a projection on their own; the
composition laws (pipe, dot, `@`, missing steps) fix how they combine, so
together they determine every path of the fragment.
"""

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr
from .strategies import at_projection, keys, missing_splits, nodes, paths, splits
from .support import depth, hits_projection

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
    through a field.
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


@given(any_node)
def test_projection_step(node):
    """Path([*]).get_data(v) = [x for x in v if x is not None] when `v` is a list, else None."""
    expected = [x for x in node if x is not None] if isinstance(node, list) else None
    assert Path(path='[*]').get_data(node) == expected


@given(splits())
def test_pipe_composes(case):
    """Path(p | q).get_data(obj) = Path(q).get_data(Path(p).get_data(obj)): the pipe nests, unconditionally.

    Records depth and projection hits of the generated paths as Hypothesis
    events.
    """
    obj, (p, q) = case
    event(f'depth {depth(obj, p | q)}')
    if hits_projection(obj, p | q):
        event('projection hit')
    assert Path(path=p | q).get_data(obj) == Path(path=q).get_data(
        Path(path=p).get_data(obj)
    )


@given(splits(head_project=False))
def test_dot_equals_pipe_without_projection(case):
    """Path(p.q).get_data(obj) = Path(p | q).get_data(obj) when `p` opens no projection: the dot nests too.

    `p` opens a projection when a `[*]` is still open at its end, that is, not
    closed by a `|` (`PathStr.opens_projection`). With one open, the two
    differ: `a[*].x` maps `x` over the list, `a[*] | x` applies `x` to the list.
    """
    obj, (p, q) = case
    assert not p.opens_projection()  # ensured by the generator
    assert Path(path=p.dot(q)).get_data(obj) == Path(path=p | q).get_data(obj)


@given(at_projection())
def test_dot_maps_under_projection(case):
    """Path(p0[*].q).get_data(obj) = [r for o in Path(p0).get_data(obj) if (r := Path(q).get_data(o)) is not None].

    When `p0` opens no projection; None when Path(p0).get_data(obj) is not a
    list. The restriction matters, since with `p0` projecting the new `[*]`
    nests inside it. On obj = {c: [[{}]]} with p0 = c[*] and q = a:

        Path(c[*][*].a).get_data(obj)                                  == [[]]
        [r for o in Path(c[*]).get_data(obj)
         if (r := Path(a).get_data(o)) is not None]                    == []

    (pinned as `test_pinned_paths[nested-projection-keeps-inner-empty]`).
    """
    obj, p0, q = case
    assert not p0.opens_projection()  # ensured by the generator
    base = Path(path=p0).get_data(obj)
    mapped = None
    if isinstance(base, list):
        mapped = [r for o in base if (r := Path(path=q).get_data(o)) is not None]
    assert Path(path=p0.dot('[*]').dot(q)).get_data(obj) == mapped


@given(paths())
def test_at_is_identity(case):
    """Path(@ | p).get_data(obj) = Path(p).get_data(obj) = Path(p | @).get_data(obj), and the same for @.p.

    The last when `p` starts with a field. `@` is the neutral element of the
    pipe on both sides and of the dot on the left only: `p.@` is not valid
    JMESPath, and `@.[*]` is a multi-select. Relative,
    Path(.@).get_data(obj) = obj.
    """
    obj, p = case
    at = PathStr('@')
    expected = Path(path=p).get_data(obj)
    assert Path(path=at.relative()).get_data(obj) == obj
    assert Path(path=at | p).get_data(obj) == expected
    assert Path(path=p | at).get_data(obj) == expected
    if p.starts_with_field():
        assert Path(path=at.dot(p)).get_data(obj) == expected


@given(missing_splits())
def test_missing_absorbs(case):
    """Path(p).get_data(obj) = None ⇒ Path(p.q).get_data(obj) = None: E(obj) is prefix-closed."""
    obj, (p, q) = case
    assume(Path(path=p).get_data(obj) is None)
    assert Path(path=p.dot(q)).get_data(obj) is None


# A list of objects in which one element lacks the field `x`.
LISTS = {'a': [{'x': {'y': 1}}, {}, {'x': {'y': 2}}]}
FIELD_ON_LIST = pytest.mark.question(1)


@pytest.mark.parametrize(
    'obj, path, expected',
    [
        pytest.param(
            LISTS, 'a[*].x', [{'y': 1}, {'y': 2}], id='projection-drops-missing'
        ),
        pytest.param(LISTS, 'a[*].x.y', [1, 2], id='projection-maps-rest'),
        pytest.param(LISTS, 'a[*].x[0]', [], id='index-per-element-on-objects'),
        pytest.param(LISTS, 'a[*].x | [0]', {'y': 1}, id='pipe-closes-projection'),
        pytest.param({'a': [1, None, 2]}, 'a[*]', [1, 2], id='projection-drops-none'),
        pytest.param({'a': {'x': 1}}, 'a[*]', None, id='projection-on-object'),
        pytest.param(
            {'c': [[]]}, 'c[*][*].a', [[]], id='nested-projection-keeps-empty'
        ),
        pytest.param(
            {'c': [[{}]]},
            'c[*][*].a',
            [[]],
            id='nested-projection-keeps-inner-empty',
        ),
        pytest.param(LISTS, 'a.x', {'y': 2}, id='field-on-list', marks=FIELD_ON_LIST),
        pytest.param(
            LISTS,
            'a[*] | x',
            {'y': 2},
            id='field-after-closed-projection',
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
        pytest.param({'a': [1, 2]}, 'a[-1]', 2, id='negative-from-end'),
        pytest.param({'a': [1, 2]}, 'a[-2]', 1, id='negative-first'),
        pytest.param(LISTS, 'a[*].x.y | [-1]', 2, id='negative-after-pipe'),
        pytest.param(
            {'a': [[1, 2], [3]]}, 'a[*][-1]', [2, 3], id='negative-per-element'
        ),
    ],
)
def test_pinned_paths(obj, path, expected):
    """Path(p).get_data(obj) on hand-picked cases, with the expected value per case."""
    assert Path(path=PathStr(path)).get_data(obj) == expected
