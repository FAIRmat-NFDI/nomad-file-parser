"""Traversal laws of `Path`, read as a crawler over nested source data.

How to read the docstrings
--------------------------

Each test states a law as a formula in its first line. The formulas use the
following tokens:

    x, v          a source value: an object, a list, a leaf or `None`
    p, q, r       paths (`p0` a path without a projection); `k` one field
                  step, written `k`, `i` one index step, written `[i]`, and
                  `s` one step of either kind
    ⟦p⟧           the meaning of `p`: the function from a source to the value
                  `p` selects in it, so ⟦p⟧(x) is `Path(path=p).get_data(x)`
    None          the failure value: ⟦p⟧(x) = None when the path stops
    p ++ q        syntax: the step list of `p` followed by that of `q`, rendered
                  as one chain with `.`; the laws say what ⟦·⟧ makes of it
    p | q         syntax: `p` and `q` as two chains joined by the pipe
    @             the current node, the path without steps
    [*]           the list projection
    .q under p    the relative child `.q` of the parent `p`
    f ∘ g         composition, right to left: (f ∘ g)(x) = f(g(x))
    mapMaybe f    the list [f(x) for x in xs if f(x) is not None]
    E(x)          the domain of `x`: the set of paths `p` that exist in `x`
    ∈, ∉          membership in, and absence from, a set such as E(x)
    ⇒             implication: if the left side holds, so does the right
    ≤, ≥          at most, at least
    p ↦ p'        a wrangler that turns the generated `p` into `p'`
    p[:i], p[i:]  the first `i` steps of `p`, and the remaining ones
    P(…)          the share of generated cases with a property

An equation between meanings, such as ⟦p | q⟧ = ⟦q⟧ ∘ ⟦p⟧, means equal
results on every source: ⟦p | q⟧(x) == ⟦q⟧(⟦p⟧(x)) for all `x`. Every
variable in a law is universally quantified over what the test's generator
produces, so a law reads "for all generated x, p, q". A clause starting with
"when" restricts that domain (for example "`p0` without `[*]`"), and the
generator enforces the restriction. `@example` pins individual cases of a
law; they run first and in every profile.

The defining equations, which the docstrings of `run_chain` and `run` spell
out in full:

    ⟦p | q⟧ = ⟦q⟧ ∘ ⟦p⟧              the pipe composes whole values
    ⟦@⟧(x) = x                       the current node
    ⟦[*] ++ q⟧(xs) = mapMaybe ⟦q⟧ xs  a projection maps the rest of its chain
    ⟦k ++ q⟧(None) = None            failure absorbs along a chain
    .q under p = p ++ q              a relative child is prepended with `.`

E(x) is prefix-closed (if p ++ q ∈ E(x), then p ∈ E(x)), which makes it a
tree domain: its leaves are the paths that cannot be extended.

The paths
---------

A path is a sequence of chains joined by `|`; a chain is a sequence of steps
(fields, integer indices, the projection `[*]`) joined by `.`. `run` below is a
reference interpreter for this fragment of JMESPath: `|` composes whole values,
`.` continues the current chain, and a projection maps the rest of its chain
over the elements, dropping `None` results. The interpreter is checked against
vanilla `jmespath` first and then serves as the oracle for `Path`.

A child path with a leading `.` inherits from its parent by prepending the
parent's path with `.`; the inheritance laws compare that with evaluating the
child on the data the parent resolved to (re-rooting).

Source and path come from one generator, `addresses`, which walks existing
addresses of the generated source; wranglers then change the path: leave the
domain (`perturbed`), cut it into parent and child (`splits`, `at_projection`)
or into chains joined by `|` (`pipelines`), or make it unparseable
(`malformed`).
"""

from copy import deepcopy
from typing import Any

import jmespath
import pytest
from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

Step = str | int
PROJECT = '*'

# Segments: three field names, so that sibling objects share keys.
keys = st.sampled_from(['a', 'b', 'c'])
# Leaves, including `None` and the falsy values that must not read as missing.
leaves = st.one_of(st.none(), st.integers(-2, 2), st.booleans(), st.just(''))


def nodes(depth: int) -> st.SearchStrategy[Any]:
    """Values nested `depth` levels deep: objects, lists of objects and lists.

    Every container at level `d` holds values of level `d - 1`; object values
    may also be leaves, so E(x) contains leaves at every depth, not only at
    the bottom.
    """
    if depth == 0:
        return leaves
    inner = nodes(depth - 1)
    objects = st.dictionaries(
        keys, st.one_of(inner, inner, leaves), min_size=1, max_size=3
    )
    return st.one_of(
        objects,
        st.lists(objects, min_size=1, max_size=3),
        st.lists(inner, min_size=1, max_size=3),
    )


# Sources: a non-empty root object of depth 2 to 4.
trees = st.sampled_from([2, 3, 4]).flatmap(
    lambda depth: st.dictionaries(keys, nodes(depth), min_size=1, max_size=3)
)
odds = st.sampled_from([True] * 9 + [False])  # True nine times in ten


@st.composite
def addresses(
    draw, project: bool = True, project_first: bool = False
) -> tuple[dict[str, Any], list[Step]]:
    """The common generator: a source `x` and a path `p ∈ E(x)`.

    The walk starts at the root and takes, at an object, an existing key
    (preferring one that continues), at a list, an index in range or `[*]`
    (continuing in one element). It stops at a leaf, at an empty container,
    or with probability 1/10 per step, so `⟦p⟧(x) is not None` except where
    a leaf holds `None`. `project=False` never takes `[*]`; `project_first`
    always takes it at the first list.
    """
    source = draw(trees)
    chain: list[Step] = []
    value: Any = source
    while isinstance(value, dict | list) and value and (not chain or draw(odds)):
        if isinstance(value, dict):
            deeper = sorted(
                k for k, v in value.items() if isinstance(v, dict | list) and v
            )
            key = draw(
                st.sampled_from(deeper if deeper and draw(odds) else sorted(value))
            )
            chain.append(key)
            value = value[key]
        elif project and (
            (project_first and PROJECT not in chain) or draw(st.booleans())
        ):
            chain.append(PROJECT)
            value = draw(st.sampled_from(value))
        else:
            index = draw(st.integers(0, len(value) - 1))
            chain.append(index)
            value = value[index]
    return source, chain


# Wranglers: take a generated address and change it


def off_domain(min_index: int = 0) -> st.SearchStrategy[Step]:
    """A step `s` that usually leaves the domain: p ++ s ∉ E(x).

    A field from `keys` (missing unless it happens to exist) or an index in
    [min_index, 3] (out of range on short lists; negative if `min_index < 0`).
    """
    return st.one_of(keys, st.integers(min_index, 3))


@st.composite
def perturbed(draw, cases, min_index: int = 0):
    """Wrangler: p ↦ p[:i] ++ s ++ p[i:] with `s` from `off_domain`, in 3/10.

    The path then stops at position `i` (missing key, out-of-range or
    negative index, or a step into a leaf); the tail after `s` is kept, so
    the absorption of the rest is exercised too.
    """
    source, chain = draw(cases)
    if draw(st.sampled_from([False] * 7 + [True] * 3)):
        at = draw(st.integers(1, len(chain)))
        chain = [*chain[:at], draw(off_domain(min_index)), *chain[at:]]
    return source, chain


@st.composite
def missing_splits(draw):
    """A source `x` and paths `p`, `q` with `p` ending in an off-domain step.

    p = a[:i] ++ s for an address `a` and `s` from `off_domain`, and
    q = a[i:]: so `p ∉ E(x)` (up to an accidental hit), built rather than
    filtered.
    """
    source, chain = draw(addresses())
    at = draw(st.integers(1, len(chain)))
    p = [*chain[:at], draw(off_domain())]
    q = chain[at:] or [draw(keys)]
    return source, (p, q)


def is_field(step: Step) -> bool:
    """Whether `step` is a field, i.e. neither an index nor `[*]`."""
    return isinstance(step, str) and step != PROJECT


@st.composite
def splits(
    draw, n: int = 2, head_project: bool = True, tail_field: bool = False
) -> tuple[dict[str, Any], list[list[Step]]]:
    """Wrangler: a perturbed address cut as p = p1 ++ … ++ pn, all non-empty.

    `head_project=False` keeps `[*]` out of p1 … p(n-1), so that no projection
    is open at a cut. `tail_field=True` makes p2 … pn start with a field, so
    that each can be written as a relative child `.pi`.
    """
    source, chain = draw(perturbed(addresses()))

    def allowed(i: int) -> bool:
        return (head_project or PROJECT not in chain[:i]) and (
            not tail_field or is_field(chain[i])
        )

    cuts = [i for i in range(1, len(chain)) if allowed(i)]
    assume(len(cuts) >= n - 1)
    chosen = sorted(draw(st.permutations(cuts))[: n - 1])
    bounds = [0, *chosen, len(chain)]
    return source, [chain[i:j] for i, j in zip(bounds, bounds[1:])]


@st.composite
def at_projection(draw, tail_field: bool = False):
    """Wrangler: a perturbed address split as p0 ++ [*] ++ q at its first `[*]`.

    `p0` contains no projection and `q` is non-empty; `tail_field=True` makes
    `q` start with a field, so that it can be written as the child `.q`.
    """
    source, chain = draw(perturbed(addresses(project_first=True)))
    assume(PROJECT in chain)
    i = chain.index(PROJECT)
    assume(i < len(chain) - 1)
    assume(not tail_field or is_field(chain[i + 1]))
    return source, chain[:i], chain[i + 1 :]


@st.composite
def pipelines(draw, min_index: int = 0):
    """Wrangler: a perturbed address cut into chains c1 | … | cm, m ≤ 3.

    `min_index < 0` lets the perturbation insert negative indices.
    """
    source, chain = draw(perturbed(addresses(), min_index))
    cuts = draw(st.sets(st.integers(1, len(chain)), max_size=2))
    bounds = [0, *sorted(cuts), len(chain)]
    return source, [chain[i:j] for i, j in zip(bounds, bounds[1:]) if chain[i:j]]


@st.composite
def malformed(draw) -> tuple[dict[str, Any], str]:
    """Wrangler: a perturbed address rendered as `p..k`, which does not parse."""
    source, chain = draw(perturbed(addresses()))
    return source, f'{render(chain)}..{draw(keys)}'


# A list of objects in which one element lacks the field `x`.
LISTS = {'a': [{'x': {'y': 1}}, {}, {'x': {'y': 2}}]}

# Pinned cases of the interpreter laws; the comment gives ⟦p⟧ as spec / `Path`.
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
]


def pinned(test):
    """Attach every case in `PINNED` to `test` as an `@example`."""
    for case in reversed(PINNED):
        test = example(case)(test)
    return test


def render(chain: list[Step]) -> str:
    """The path string of a chain: fields joined by `.`, `[i]` and `[*]` attached."""
    out = ''
    for step in chain:
        if step == PROJECT:
            out += '[*]'
        elif isinstance(step, int):
            out += f'[{step}]'
        else:
            out += f'.{step}' if out else step
    return out


def render_pipeline(pipeline: list[list[Step]]) -> str:
    """The path string c1 | … | cm of a list of chains."""
    return ' | '.join(render(chain) for chain in pipeline)


def run_chain(chain: list[Step], value: Any, last_on_list: bool = False) -> Any:
    """The reference interpreter of one chain, defined by recursion on its steps:

        ⟦[]⟧(v)           = v
        ⟦[*] ++ q⟧(v)     = mapMaybe ⟦q⟧ v      if v is a list, else None
        ⟦[i] ++ q⟧(v)     = ⟦q⟧(v[i])           if i is in range, else ⟦q⟧(None)
        ⟦k ++ q⟧(v)       = ⟦q⟧(v.get(k))       if v is an object, else ⟦q⟧(None)

    so `None` absorbs along a chain and a projection captures the rest of
    it. `last_on_list` adds `Path`'s rule ⟦k⟧(xs) = ⟦k⟧(xs[-1]) for a
    field on a non-empty list.
    """
    if not chain:
        return value
    step, rest = chain[0], chain[1:]
    if step == PROJECT:
        if not isinstance(value, list):
            return None
        results = (run_chain(rest, x, last_on_list) for x in value)
        return [r for r in results if r is not None]
    if isinstance(step, int):
        found = isinstance(value, list) and -len(value) <= step < len(value)
        return run_chain(rest, value[step] if found else None, last_on_list)
    if last_on_list and isinstance(value, list):
        value = value[-1] if value else None
    found = isinstance(value, dict)
    return run_chain(rest, value.get(step) if found else None, last_on_list)


def run(pipeline: list[list[Step]], value: Any, last_on_list: bool = False) -> Any:
    """The reference interpreter of c1 | … | cm: ⟦cm⟧ ∘ … ∘ ⟦c1⟧."""
    for chain in pipeline:
        value = run_chain(chain, value, last_on_list)
    return value


def get(path: str, source: Any) -> Any:
    """⟦path⟧(source) as evaluated by `Path`, the implementation under test."""
    return Path(path=path).get_data(source)


def depth(source: Any, chain: list[Step]) -> int:
    """max {k : ⟦chain[:k]⟧(source) ∉ {None, []}}, how far the path reaches."""
    reached = [
        k
        for k in range(len(chain) + 1)
        if run_chain(chain[:k], source, True) not in (None, [])
    ]
    return max(reached, default=0)


def hits_projection(source: Any, chain: list[Step]) -> bool:
    """Whether some `[*]` in the chain maps over a non-empty result."""
    return any(
        step == PROJECT and run_chain(chain[: i + 1], source, True) not in (None, [])
        for i, step in enumerate(chain)
    )


def test_addresses_reach_into_the_data():
    """Guard on the generator: P(depth ≥ 2) ≥ 1/2 and P(projection hit) ≥ 1/5.

    Paths that stop at the first step satisfy every law below as None == None;
    this fails when the generator drifts back to such paths.
    """
    depths, hits = [], []

    @settings(max_examples=300, derandomize=True, database=None)
    @given(perturbed(addresses()))
    def sample(case):
        source, chain = case
        depths.append(depth(source, chain))
        hits.append(hits_projection(source, chain))

    sample()
    assert sum(d >= 2 for d in depths) / len(depths) >= 0.5
    assert sum(hits) / len(hits) >= 0.2


# The interpreter against the references


@given(pipelines(min_index=-3))
@pinned
def test_interpreter_matches_jmespath(case):
    """run(p)(x) = jmespath(p)(x): the interpreter is the spec on this fragment.

    Includes negative indices; this validates the definitions before they
    serve as the oracle for `Path`.
    """
    source, pipeline = case
    expected = jmespath.search(render_pipeline(pipeline), source)
    assert run(pipeline, source) == expected


@given(pipelines())
@pinned
def test_interpreter_matches_path(case):
    """⟦p⟧(x) = run(p, last_on_list)(x): `Path` is the spec plus the last-element rule.

    Negative indices are excluded, since reading them can mutate `x`
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


# Delimiter laws, stated on `Path`


@given(splits())
def test_pipe_composes(case):
    """⟦p | q⟧ = ⟦q⟧ ∘ ⟦p⟧: the pipe is the crawler's nesting law, unconditionally."""
    source, (p, q) = case
    assert get(f'{render(p)} | {render(q)}', source) == get(
        render(q), get(render(p), source)
    )


@given(splits(head_project=False))
def test_dot_equals_pipe_without_projection(case):
    """⟦p ++ q⟧ = ⟦p | q⟧ when `p` contains no `[*]`: the dot nests like the pipe."""
    source, (p, q) = case
    assert get(render(p + q), source) == get(f'{render(p)} | {render(q)}', source)


@given(at_projection())
@example(({'c': [[]]}, ['c'], [PROJECT, 'a']))
def test_dot_maps_under_projection(case):
    """⟦p0 ++ [*] ++ q⟧ = mapMaybe ⟦q⟧ ∘ ⟦p0⟧ when `p0` contains no `[*]`.

    The dot after a projection is the lifted step, not the step. The
    restriction matters: if `p0` projects, the appended `[*] ++ q` is
    captured by it and maps over the inner elements (the pinned example,
    where ⟦c[*][*].a⟧ = [[]] but mapMaybe ⟦[*].a⟧ [[]] = []).
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
    """⟦@ | p⟧ = ⟦p⟧ = ⟦p | @⟧, and ⟦@ ++ p⟧ = ⟦p⟧ when `p` starts with a field.

    `@` is the neutral element of the pipe on both sides and of the dot on
    the left only: `p.@` is not valid JMESPath. Relative, ⟦.@⟧ = ⟦@⟧.
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
    """⟦p⟧(x) = None ⇒ ⟦p ++ q⟧(x) = None: E(x) is prefix-closed."""
    source, (p, q) = case
    assume(get(render(p), source) is None)
    assert get(render(p + q), source) is None


@pytest.mark.xfail(strict=True, reason='negative out-of-range index pads the list')
@given(pipelines(min_index=-3))
@example(({'a': [1, 2]}, [['a', -3]]))
def test_get_does_not_mutate_source(case):
    """x after ⟦p⟧(x) = x before: reading has no effect on the source.

    Fails for a negative index past the start, which `visit_index` pads in
    search mode: ⟦a[-3]⟧({a: [1, 2]}) = 1 and leaves {a: [1, 2, {}]}.
    """
    source, pipeline = case
    before = deepcopy(source)
    get(render_pipeline(pipeline), source)
    assert source == before


# Inheritance by the relative prefix


def inherit(parent: list[Step], child: list[Step]) -> Path:
    """The `Path` of the child `.child` under `parent`."""
    return Path(path='.' + render(child), parent=Path(path=render(parent)))


@given(splits(head_project=False, tail_field=True))
def test_prefix_equals_reroot(case):
    """.q under p: absolute path p ++ q, and ⟦p ++ q⟧ = ⟦q⟧ ∘ ⟦p⟧ for `p` without `[*]`.

    Prepending (static) and re-rooting (runtime) agree: removing the prefix
    `p` moves the root down to ⟦p⟧(x).
    """
    source, (parent, child) = case
    child_path = inherit(parent, child)
    assert child_path.absolute_path == render(parent + child)
    rerooted = get(child_path.relative_path, get(render(parent), source))
    assert get(child_path.absolute_path, source) == rerooted


@given(at_projection(tail_field=True))
def test_projecting_parent_maps_child(case):
    """.q under p0 ++ [*]: ⟦p0 ++ [*] ++ q⟧ = mapMaybe ⟦q⟧ ∘ ⟦p0⟧, `p0` without `[*]`.

    A projecting parent applies its child per element, which is what the
    mapper does when a section's source resolves to a list.
    """
    source, p0, child = case
    child_path = inherit(p0 + [PROJECT], child)
    base = get(render(p0), source)
    mapped = None
    if isinstance(base, list):
        results = (get(child_path.relative_path, x) for x in base)
        mapped = [r for r in results if r is not None]
    assert get(child_path.absolute_path, source) == mapped


@given(splits(n=3, head_project=False, tail_field=True))
def test_parent_chain_is_associative(case):
    """.r under .q under p: absolute path (p ++ q) ++ r, and ⟦p ++ q ++ r⟧ = ⟦r⟧ ∘ ⟦q⟧ ∘ ⟦p⟧.

    Prepending along a chain of parents is associative and agrees with
    re-rooting step by step, for parents without `[*]`.
    """
    source, (grandparent, parent, child) = case
    child_path = Path(
        path='.' + render(child),
        parent=Path(path='.' + render(parent), parent=Path(path=render(grandparent))),
    )
    assert child_path.absolute_path == render(grandparent + parent + child)
    stepwise = get(render(child), get(render(parent), get(render(grandparent), source)))
    assert get(child_path.absolute_path, source) == stepwise


# The relative prefix and `default`


@given(pipelines())
def test_prefix_is_dropped(case):
    """⟦.p⟧ = ⟦p⟧: on its own, the leading `.` only marks `p` as relative."""
    source, pipeline = case
    path = render_pipeline(pipeline)
    assert get('.' + path, source) == get(path, source)


@given(trees)
def test_bare_prefix_is_empty(source):
    """⟦.⟧ = None: a bare `.` is the prefix of the empty expression, not `@`."""
    assert get('.', source) is None


@given(pipelines())
@example(({'a': [1, 2]}, [['a']]))  # length(a) is 2, length(.a) does not parse
def test_prefix_in_function_does_not_parse(case):
    """⟦f(.p)⟧ = None for a function `f`: the prefix is stripped only at the
    start of the path and after whitespace, so inside a call it stays."""
    source, pipeline = case
    assert get(f'length(.{render_pipeline(pipeline)})', source) is None


@given(pipelines())
@example(({'a': {}}, [['a', 'x']]))  # missing: None, not the default
def test_default_ignored_when_parseable(case):
    """⟦p⟧ with `default=d` = ⟦p⟧ when `p` parses, also when `p ∉ E(x)`."""
    source, pipeline = case
    path = Path(path=render_pipeline(pipeline))
    assert path.get_data(source, default='DEFAULT') == path.get_data(source)


@given(malformed())
def test_default_replaces_parse_errors(case):
    """⟦p⟧ with `default=d` = d when `p` does not parse."""
    source, path = case
    assert Path(path=path).get_data(source, default='DEFAULT') == 'DEFAULT'
