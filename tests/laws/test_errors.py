"""Malformed, relative and out-of-range input: purity of reads, functions, `default`."""

from copy import deepcopy

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr
from .strategies import malformed, pipelines, splits, trees


@pytest.mark.question(2)
@pytest.mark.xfail(strict=True, reason='negative out-of-range index pads the list')
@given(pipelines(min_index=-3))
@example(({'a': [1, 2]}, PathStr('a[-3]')))
def test_get_does_not_mutate_source(case):
    """obj after Path(p).get_data(obj) = obj before: reading has no effect on the object.

    Agreed (question 2). Fails for a negative index past the start, which
    `visit_index` pads in search mode: Path(a[-3]).get_data({a: [1, 2]}) = 1
    and leaves {a: [1, 2, {}]}.
    """
    obj, path = case
    before = deepcopy(obj)
    Path(path=path).get_data(obj)
    assert obj == before


@pytest.mark.question(5)
@given(trees)
def test_bare_prefix_is_empty(obj):
    """Path(.).get_data(obj) = None: a bare `.` is the prefix of the empty expression, not `@`.

    The current node is written `@` (`test_at_is_current`) or `.@`.
    """
    assert Path(path='.').get_data(obj) is None


@pytest.mark.question(4)
@pytest.mark.xfail(
    strict=True, reason='a relative path inside a function does not parse'
)
@given(pipelines())
@example(({'a': [1, 2]}, PathStr('a')))
def test_relative_path_in_function(case):
    """Path(not_null(.p)).get_data(obj) = Path(p).get_data(obj): a relative path in a call is evaluated.

    Agreed (question 4): `.p` inside a function call is read like `.p` on its
    own, and its value, `None` included, is passed to the function.
    `not_null` returns its argument unchanged, so the law isolates the
    path; on {a: [1, 2]}, `length(.a)` is then 2. Fails today: the prefix is
    stripped only at the start of the path, so the call does not parse and
    the read gives `None`.
    """
    obj, path = case
    assert Path(path=f'not_null({path.relative()})').get_data(obj) == Path(
        path=path
    ).get_data(obj)


@pytest.mark.question(4)
@pytest.mark.xfail(
    strict=True, reason='a relative path inside a function does not parse'
)
@given(splits(head_project=False, tail_field=True))
def test_relative_path_in_function_under_parent(case):
    """.q under p inside a call: absolute path not_null(p.q), and Path(not_null(.q)) on Path(p).get_data(obj) = Path(p.q).get_data(obj).

    Agreed (question 4): the parent is prepended inside the call, as it is
    for a relative path on its own (`test_prefix_equals_reroot`), and the
    child read on the parent's value agrees with the absolute path.
    """
    obj, (parent, child) = case
    path = Path(path=f'not_null({child.relative()})', parent=Path(path=parent))
    assert path.absolute_path == f'not_null({parent.dot(child)})'
    expected = Path(path=parent.dot(child)).get_data(obj)
    assert path.get_data(Path(path=parent).get_data(obj)) == expected
    assert Path(path=path.absolute_path).get_data(obj) == expected


@pytest.mark.question(6)
@given(st.one_of(pipelines(), malformed()))
@example(({'a': {}}, PathStr('a.x')))  # `x` is missing: None, not the default
def test_default_replaces_only_parse_errors(case):
    """Path(p).get_data(obj, default=d) = d if `p` does not parse, else Path(p).get_data(obj).

    Today's behaviour: a path that parses but finds nothing gives `None`, not
    the default. Question 6 records the two positions on whether `default`
    should also replace a missing value. Malformed paths are plain `str`, not
    `PathStr`.
    """
    obj, path = case
    expected = Path(path=path).get_data(obj) if isinstance(path, PathStr) else 'DEFAULT'
    assert Path(path=path).get_data(obj, default='DEFAULT') == expected
