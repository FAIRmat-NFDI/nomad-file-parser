"""Malformed and out-of-range input: purity of reads, parse errors, `default`."""

from copy import deepcopy

import pytest
from hypothesis import example, given

from nomad_file_parser.mapping_parser import Path

from .reference import get
from .strategies import malformed, pipelines, render_pipeline, trees


@pytest.mark.question(2)
@pytest.mark.xfail(strict=True, reason='negative out-of-range index pads the list')
@given(pipelines(min_index=-3))
@example(({'a': [1, 2]}, [['a', -3]]))
def test_get_does_not_mutate_source(case):
    """x after eval(p)(x) = x before: reading has no effect on the source.

    Fails for a negative index past the start, which `visit_index` pads in
    search mode: eval(a[-3])({a: [1, 2]}) = 1 and leaves {a: [1, 2, {}]}.
    """
    source, pipeline = case
    before = deepcopy(source)
    get(render_pipeline(pipeline), source)
    assert source == before


@pytest.mark.question(5)
@given(trees)
def test_bare_prefix_is_empty(source):
    """eval(.) = None: a bare `.` is the prefix of the empty expression, not `@`."""
    assert get('.', source) is None


@pytest.mark.question(4)
@given(pipelines())
@example(({'a': [1, 2]}, [['a']]))  # length(a) is 2, length(.a) does not parse
def test_prefix_in_function_does_not_parse(case):
    """eval(f(.p)) = None for a function `f`: a relative path does not parse in a call.

    The prefix is stripped only at the start of the path and after
    whitespace, so inside a call it stays.
    """
    source, pipeline = case
    assert get(f'length(.{render_pipeline(pipeline)})', source) is None


@pytest.mark.question(6)
@given(pipelines())
@example(({'a': {}}, [['a', 'x']]))  # missing: None, not the default
def test_default_ignored_when_parseable(case):
    """eval_d(p) = eval(p) when `p` parses, also when `p ∉ E(x)`."""
    source, pipeline = case
    path = Path(path=render_pipeline(pipeline))
    assert path.get_data(source, default='DEFAULT') == path.get_data(source)


@pytest.mark.question(6)
@given(malformed())
def test_default_replaces_parse_errors(case):
    """eval_d(p)(x) = d when `p` does not parse."""
    source, path = case
    assert Path(path=path).get_data(source, default='DEFAULT') == 'DEFAULT'
