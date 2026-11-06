"""Traversal: how the steps of a path compose.

Pipe, dot, projection, `@`, and the absorption of a missing step.
"""

from copy import deepcopy

import pytest
from hypothesis import assume, event, example, given

from .reference import depth, get, hits_projection, run
from .strategies import (
    PROJECT,
    addresses,
    at_projection,
    is_field,
    missing_splits,
    perturbed,
    pipelines,
    render,
    render_pipeline,
    splits,
)

# A list of objects in which one element lacks the field `x`.
LISTS = {'a': [{'x': {'y': 1}}, {}, {'x': {'y': 2}}]}

# Pinned cases of the traversal laws; the comment gives the value of `run`, then
# that of `Path` where they differ.
PINNED = [
    (LISTS, [['a', PROJECT, 'x']]),  # [{y: 1}, {y: 2}]: drops the missing `x`
    (LISTS, [['a', PROJECT, 'x', 'y']]),  # [1, 2]: maps the rest of the chain
    (LISTS, [['a', PROJECT, 'x', 0]]),  # []: `[0]` per element, on objects
    (LISTS, [['a', PROJECT, 'x'], [0]]),  # {y: 1}: `|` closes the projection
    ({'a': [1, None, 2]}, [['a', PROJECT]]),  # [1, 2]: drops `None` elements
    ({'a': {'x': 1}}, [['a', PROJECT]]),  # None: `[*]` on an object
    ({'c': [[]]}, [['c', PROJECT, PROJECT, 'a']]),  # [[]]: nested keeps empty
    (LISTS, [['a', 'x']]),  # None / {y: 2}: field on a list
    (LISTS, [['a', PROJECT], ['x']]),  # None / {y: 2}: after a closed projection
    ({'a': []}, [['a', 'x']]),  # None: field on an empty list
    ({'a': [1, 2]}, [['a', 'x']]),  # None: field on a list of scalars
    ({'a': {}}, [['a', 'x']]),  # None: missing
    ({'a': {'n': None}}, [['a', 'n']]),  # None: holds `None`, same as missing
    ({'a': {'b': 0}}, [['a', 'b', 'c']]),  # None: into a leaf, same as missing
    ({'a': {'e': {}}}, [['a', 'e']]),  # {}: an empty object is a value
    ({'a': {'z': 0}}, [['a', 'z']]),  # 0: falsy leaves are values
    ({'a': {'f': False}}, [['a', 'f']]),  # False
    ({'a': {'s': ''}}, [['a', 's']]),  # ''
    ({'a': [1, 2]}, [['a', -1]]),  # 2: negative index from the end
    ({'a': [1, 2]}, [['a', -2]]),  # 1: the first element, still in range
    (LISTS, [['a', PROJECT, 'x', 'y'], [-1]]),  # 2: negative after `|`
    ({'a': [[1, 2], [3]]}, [['a', PROJECT, -1]]),  # [2, 3]: per element
]


def pinned(test):
    """Attach every case in `PINNED` to `test` as an `@example`."""
    for case in reversed(PINNED):
        test = example(case)(test)
    return test


@pytest.mark.question(1)
@given(pipelines())
@pinned
def test_path_matches_reference(case):
    """eval(p)(x) = run(p, last_on_list)(x): `Path` agrees with the reference, field-on-list rule included.

    Negative indices are included where they are in range (the walk takes
    -len … len - 1); the perturbation inserts only non-negative off-domain
    indices, since reading a negative one past the start mutates `x`
    (`test_get_does_not_mutate_source`). Records depth and projection hits
    as Hypothesis events.
    """
    source, pipeline = case
    chain = [step for part in pipeline for step in part]
    event(f'depth {depth(source, chain)}')
    if hits_projection(source, chain):
        event('projection hit')
    expected = run(pipeline, deepcopy(source), last_on_list=True)
    assert get(render_pipeline(pipeline), source) == expected


@given(splits())
def test_pipe_composes(case):
    """eval(p | q) = eval(q) ∘ eval(p): the pipe is the crawler's nesting law, unconditionally."""
    source, (p, q) = case
    assert get(f'{render(p)} | {render(q)}', source) == get(
        render(q), get(render(p), source)
    )


@given(splits(head_project=False))
def test_dot_equals_pipe_without_projection(case):
    """eval(p ++ q) = eval(p | q) when `p` contains no `[*]`: the dot nests like the pipe."""
    source, (p, q) = case
    assert get(render(p + q), source) == get(f'{render(p)} | {render(q)}', source)


@given(at_projection())
@example(({'c': [[]]}, ['c'], [PROJECT, 'a']))
def test_dot_maps_under_projection(case):
    """eval(p0 ++ [*] ++ q) = mapMaybe eval(q) ∘ eval(p0) when `p0` contains no `[*]`.

    The dot after a projection is the lifted step, not the step. The
    restriction matters: if `p0` projects, the appended `[*] ++ q` is
    captured by it and maps over the inner elements (the pinned example,
    where eval(c[*][*].a) = [[]] but mapMaybe eval([*].a) [[]] = []).
    """
    source, p0, q = case
    base = get(render(p0), source)
    mapped = None
    if isinstance(base, list):
        results = (get(render(q), x) for x in base)
        mapped = [r for r in results if r is not None]
    assert get(render(p0 + [PROJECT] + q), source) == mapped


@given(perturbed(addresses()))
def test_at_is_identity(case):
    """eval(@ | p) = eval(p) = eval(p | @), and eval(@ ++ p) = eval(p) when `p` starts with a field.

    `@` is the neutral element of the pipe on both sides and of the dot on
    the left only: `p.@` is not valid JMESPath. Relative, eval(.@) = eval(@).
    """
    source, p = case
    path = render(p)
    assert get('.@', source) == source
    assert get(f'@ | {path}', source) == get(path, source)
    assert get(f'{path} | @', source) == get(path, source)
    if is_field(p[0]):  # '@.[*]' is a multi-select, '@.[0]' does not parse
        assert get(f'@.{path}', source) == get(path, source)


@given(missing_splits())
def test_missing_absorbs(case):
    """eval(p)(x) = None ⇒ eval(p ++ q)(x) = None: E(x) is prefix-closed."""
    source, (p, q) = case
    assume(get(render(p), source) is None)
    assert get(render(p + q), source) is None
