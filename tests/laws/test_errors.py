"""Malformed and out-of-range input: purity of reads, parse errors, `default`."""

from copy import deepcopy

import pytest
from hypothesis import example, given

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr
from .strategies import malformed, pipelines, trees


@pytest.mark.question(2)
@pytest.mark.xfail(strict=True, reason='negative out-of-range index pads the list')
@given(pipelines(min_index=-3))
@example(({'a': [1, 2]}, PathStr('a[-3]')))
def test_get_does_not_mutate_source(case):
    """obj after Path(p).get_data(obj) = obj before: reading has no effect on the object.

    Fails for a negative index past the start, which `visit_index` pads in
    search mode: Path(a[-3]).get_data({a: [1, 2]}) = 1 and leaves {a: [1, 2, {}]}.
    """  # TODO: bug?
    obj, path = case
    before = deepcopy(obj)
    Path(path=path).get_data(obj)
    assert obj == before


@pytest.mark.question(5)
@given(trees)
def test_bare_prefix_is_empty(obj):
    """Path(.).get_data(obj) = None: a bare `.` is the prefix of the empty expression, not `@`."""
    assert Path(path='.').get_data(obj) is None


@pytest.mark.question(4)
@given(pipelines())
@example(({'a': [1, 2]}, PathStr('a')))  # length(a) is 2, length(.a) does not parse
def test_prefix_in_function_does_not_parse(case):
    """Path(f(.p)).get_data(obj) = None for a function `f`: a relative path does not parse in a call.

    The prefix is stripped only at the start of the path and after
    whitespace, so inside a call it stays.
    """
    obj, path = case
    assert Path(path=f'length({path.relative()})').get_data(obj) is None


@pytest.mark.question(6)
@given(pipelines())
@example(({'a': {}}, PathStr('a.x')))  # missing: None, not the default
def test_default_ignored_when_parseable(case):
    """Path(p).get_data(obj, default=d) = Path(p).get_data(obj) when `p` parses, also when p ∉ E(obj)."""
    obj, path = case
    assert Path(path=path).get_data(obj, default='DEFAULT') == Path(path=path).get_data(
        obj
    )


@pytest.mark.question(6)
@given(malformed())
def test_default_replaces_parse_errors(case):
    """Path(p).get_data(obj, default=d) = d when `p` does not parse (a plain `str`, not a `PathStr`)."""
    obj, path = case
    assert Path(path=path).get_data(obj, default='DEFAULT') == 'DEFAULT'
