"""Traversal laws of `Path`, read as a crawler over nested source data.

How to read the docstrings
--------------------------

Each test states a law as a formula in its first line. The formulas use the
following tokens:

    Value         object | list | leaf | None, the values of sources and of
                  results alike (results include `[]` and nested lists)
    x, v          a source value, of type Value
    p, q, r       paths (`p0` a path without a projection); `k` one field
                  step, written `k`, `i` one index step, written `[i]`, and
                  `s` one step of either kind
    eval          path → Value → Value, curried: eval(p) is the meaning
                  of the path `p`, the function from a source to the value
                  `p` selects in it, so eval(p)(x) is
                  `Path(path=p).get_data(x)` and eval(q) can be passed on, as
                  in mapMaybe eval(q) xs
    eval_d        the same with a fallback d: Value, eval_d(p)(x) is
                  `Path(path=p).get_data(x, default=d)`; eval = eval_None
    None          the failure value: eval(p)(x) = None when the path stops
    p ++ q        syntax: the step list of `p` followed by that of `q`, rendered
                  as one chain with `.`; the laws say what eval(·) makes of it
    p | q         syntax: `p` and `q` as two chains joined by the pipe
    @             the current node, the path without steps
    [*]           the list projection
    .q under p    the relative child `.q` of the parent `p`
    f ∘ g         composition, right to left: (f ∘ g)(x) = f(g(x))
    mapMaybe f    the list [f(x) for x in xs if f(x) is not None]
    E(x)          the domain of `x`: the set of paths `p` that exist in `x`
    ∈, ∉          membership in, and absence from, a set such as E(x)
    v ! s         the child of `v` at the field or index step `s`, None if
                  there is none
    ⇒             implication: if the left side holds, so does the right
    ≤, ≥          at most, at least
    p ↦ p'        a wrangler that turns the generated `p` into `p'`
    p[:i], p[i:]  the first `i` steps of `p`, and the remaining ones
    P(…)          the share of generated cases with a property

An equation between meanings, such as eval(p | q) = eval(q) ∘ eval(p),
means equal results on every source: eval(p | q)(x) == eval(q)(eval(p)(x))
for all `x`. Every variable in a law is universally quantified over what the
test's generator produces, so a law reads "for all generated x, p, q". A
clause starting with "when" restricts that domain (for example "`p0` without
`[*]`"), and the generator enforces the restriction. `@example` pins individual cases of a
law; they run first and in every profile.

The defining equations, which the docstrings of `run_chain` and `run` spell
out in full:

    eval(p | q) = eval(q) ∘ eval(p)           the pipe composes whole values
    eval(@)(x) = x                            the current node
    eval([*] ++ q)(xs) = mapMaybe eval(q) xs  a projection maps the rest of
                                              its chain
    eval(k ++ q)(None) = None                 failure absorbs along a chain
    .q under p = p ++ q                       a relative child is prepended
                                              with `.`

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

The mapper tree
---------------

The last section states how projections compose across nested sections of a
`Mapper`, on the tree `C` (source `c`) → `S` (source `.s`) → `E` (path `.e`).
M_K,L(x) is its result with `indices=K` on `C` and `indices=L` on `S`, where
`[]` requests every element as a list and `None` a single value; values(…)
reads the `E` values of a result as nested lists. The joined path
`c[*].s[*].e` serves as the oracle. Pinned cases record current behaviour
that `OPEN_QUESTIONS.md` asks about.

Polymorphic subsections
-----------------------

The polymorphism laws use an unannotated base `Shape` with the subclasses
`Circle`, `Square` and `Triangle`, one field each, under the repeating
subsections of `Drawing`. The mapper defers from the base to every subclass
annotated under the active key; `from_dict` resolves each element's type from
its `m_def`.
"""

from copy import deepcopy
from typing import Any

import jmespath
import pytest
from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st
from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import Mapper as MapperAnnotation
from nomad.metainfo import Quantity, SubSection

from nomad_file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    Mapper,
    MappingParser,
    MetainfoParser,
    Path,
)

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
    (preferring one that continues), at a list, an index in range (negative
    ones included) or `[*]`
    (continuing in one element). It stops at a leaf, at an empty container,
    or with probability 1/10 per step, so `eval(p)(x) is not None` except where
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
            index = draw(st.integers(-len(value), len(value) - 1))
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

# Pinned cases of the interpreter laws; the comment gives eval(p) as spec / `Path`.
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

        eval([])(v)       = v
        eval([*] ++ q)(v) = mapMaybe eval(q) v   if v is a list, else None
        eval(s ++ q)(v)   = eval(q)(v ! s)

    where v ! s is the child of `v` at the field or index step `s`, and
    None when there is none: `v` is not an object (for `k`) or not a list
    (for `[i]`), or the key is missing or the index out of range. So `None`
    absorbs along a chain and a projection captures the rest of it.
    `last_on_list` adds `Path`'s rule eval(k)(xs) = eval(k)(xs[-1]) for a
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
    """The reference interpreter of c1 | … | cm: eval(cm) ∘ … ∘ eval(c1)."""
    for chain in pipeline:
        value = run_chain(chain, value, last_on_list)
    return value


def get(path: str, source: Any) -> Any:
    """eval(path)(source) as evaluated by `Path`, the implementation under test."""
    return Path(path=path).get_data(source)


def depth(source: Any, chain: list[Step]) -> int:
    """max {k : eval(chain[:k])(source) ∉ {None, []}}, how far the path reaches."""
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
    """eval(p)(x) = run(p, last_on_list)(x): `Path` is the spec plus the last-element rule.

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


# Delimiter laws, stated on `Path`


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


# Inheritance by the relative prefix


def inherit(parent: list[Step], child: list[Step]) -> Path:
    """The `Path` of the child `.child` under `parent`."""
    return Path(path='.' + render(child), parent=Path(path=render(parent)))


@given(splits(head_project=False, tail_field=True))
def test_prefix_equals_reroot(case):
    """.q under p: absolute path p ++ q, and eval(p ++ q) = eval(q) ∘ eval(p) for `p` without `[*]`.

    Prepending (static) and re-rooting (runtime) agree: removing the prefix
    `p` moves the root down to eval(p)(x).
    """
    source, (parent, child) = case
    child_path = inherit(parent, child)
    assert child_path.absolute_path == render(parent + child)
    rerooted = get(child_path.relative_path, get(render(parent), source))
    assert get(child_path.absolute_path, source) == rerooted


@given(at_projection(tail_field=True))
def test_projecting_parent_maps_child(case):
    """.q under p0 ++ [*]: eval(p0 ++ [*] ++ q) = mapMaybe eval(q) ∘ eval(p0), `p0` without `[*]`.

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
    """.r under .q under p: absolute path (p ++ q) ++ r, and eval(p ++ q ++ r) = eval(r) ∘ eval(q) ∘ eval(p).

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
    """eval(.p) = eval(p): on its own, the leading `.` only marks `p` as relative."""
    source, pipeline = case
    path = render_pipeline(pipeline)
    assert get('.' + path, source) == get(path, source)


@given(trees)
def test_bare_prefix_is_empty(source):
    """eval(.) = None: a bare `.` is the prefix of the empty expression, not `@`."""
    assert get('.', source) is None


@given(pipelines())
@example(({'a': [1, 2]}, [['a']]))  # length(a) is 2, length(.a) does not parse
def test_prefix_in_function_does_not_parse(case):
    """eval(f(.p)) = None for a function `f`: the prefix is stripped only at the
    start of the path and after whitespace, so inside a call it stays."""
    source, pipeline = case
    assert get(f'length(.{render_pipeline(pipeline)})', source) is None


@given(pipelines())
@example(({'a': {}}, [['a', 'x']]))  # missing: None, not the default
def test_default_ignored_when_parseable(case):
    """eval_d(p) = eval(p) when `p` parses, also when `p ∉ E(x)`."""
    source, pipeline = case
    path = Path(path=render_pipeline(pipeline))
    assert path.get_data(source, default='DEFAULT') == path.get_data(source)


@given(malformed())
def test_default_replaces_parse_errors(case):
    """eval_d(p)(x) = d when `p` does not parse."""
    source, path = case
    assert Path(path=path).get_data(source, default='DEFAULT') == 'DEFAULT'


# Projections across the mapper tree


class SourceParser(MappingParser):
    """A parser over an in-memory source, as the mapper needs one to run."""

    def from_dict(self, dct: dict[str, Any]) -> None:
        return super().from_dict(dct)  # type: ignore

    def load_file(self) -> Any:
        return super().load_file()

    def to_dict(self, **kwargs) -> dict[str | int, Any]:
        return super().to_dict(**kwargs)


JOINED = 'c[*].s[*].e'

# SCF steps: with a leaf `e`, or without one.
steps = st.one_of(st.integers(-2, 2).map(lambda e: {'e': e}), st.just({'x': 0}))
# Calculations: steps (possibly none), or no `s` at all.
calculations = st.one_of(
    st.lists(steps, max_size=3).map(lambda s: {'s': s}), st.just({})
)
sources = st.lists(calculations, max_size=4).map(lambda c: {'c': c})
# Sources in which every calculation has at least one step with a leaf.
dense = st.lists(
    st.lists(st.integers(-2, 2), min_size=1, max_size=3), min_size=1, max_size=4
).map(lambda c: {'c': [{'s': [{'e': e} for e in s]} for s in c]})


def section(target: str, source: str, mappers: list, indices: list[int] | None):
    """The spec of a section mapper; `indices=None` leaves the key unset."""
    spec = dict(target=target, source=source, mapper=mappers)
    if indices is not None:
        spec['indices'] = indices
    return spec


def run_mapper(specs: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    """The result of the mapper built from `specs` on a copy of `source`."""
    source = deepcopy(source)
    mapper = Mapper.from_dict({'mapper': specs})
    return mapper.get_data(source, SourceParser(data=source))


def tree(source, outer: list[int] | None = [], inner: list[int] | None = []):
    """M_K,L(x) with K = `outer` and L = `inner`."""
    leaf = dict(target='E', path='.e')
    specs = [section('C', 'c', [section('S', '.s', [leaf], inner)], outer)]
    return run_mapper(specs, source)


def values(result: dict[str, Any]) -> list[list[Any]]:
    """The `E` values of a repeating `C` → repeating `S` result as nested lists."""
    return [[s['E'] for s in c['S']] for c in result.get('C', [])]


def per_element(source: dict[str, Any]) -> list[list[Any]]:
    """eval(s[*].e) on each calculation by source position, `[]` where it fails."""
    return [get('s[*].e', c) or [] for c in source['c']]


@given(dense)
def test_nested_sections_follow_joined_path(source):
    """values(M_[],[](x)) = eval(c[*].s[*].e)(x) when every element has a leaf.

    Nesting repeating sections composes like `.` in a path: one list level
    per section.
    """
    assert values(tree(source)) == get(JOINED, source)


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


@given(sources)
def test_unindexed_outer_takes_first(source):
    """M_None,[](x) = {C: c1} for the first non-empty repeat c1 of M_[],[](x).

    Without `indices`, a section keeps only the first non-empty element of a
    list source (question 7); `{}` when there is none.
    """
    repeats = tree(source).get('C', [])
    expected = {'C': repeats[0]} if repeats else {}
    assert tree(source, outer=None) == expected


@given(sources)
def test_unindexed_inner_takes_first(source):
    """M_[],None(x)[C][i] = {S: {E: l[0]}} for each non-empty l in values(M_[],[](x)).

    The same rule one level down: each calculation keeps its first step with
    a leaf, not a list of them.
    """
    expected = [{'S': {'E': inner[0]}} for inner in values(tree(source))]
    assert tree(source, inner=None).get('C', []) == expected


@st.composite
def indexed(draw):
    """A source with at least one calculation and a non-empty subset K of its positions."""
    source = draw(sources.filter(lambda x: x['c']))
    positions = st.integers(0, len(source['c']) - 1)
    return source, sorted(draw(st.sets(positions, min_size=1)))


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


TWO = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': [{'e': 3}]}]}
GAP = {'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': []}, {'s': [{'e': 3}]}]}
TREE_TWO = {'C': [{'S': [{'E': 1}, {'E': 2}]}, {'S': [{'E': 3}]}]}


def leaf_under(source: str) -> list[dict[str, Any]]:
    """One repeating section `S` with source `source` and the quantity `E` = `.e`."""
    return [section('S', source, [dict(target='E', path='.e')], [])]


@pytest.mark.parametrize(
    'specs, source, expected',
    [
        pytest.param(
            None,
            GAP,
            {'C': [{'S': [{'E': 1}, {'E': 2}]}, {'S': [{'E': 3}]}]},
            id='missing-vs-empty',
        ),
        pytest.param(
            leaf_under('c[*].s[*]'),
            TWO,
            {'S': [{'E': 1}, {'E': 3}]},
            id='source-double-projection',
        ),
        pytest.param(
            leaf_under('c[*].s'),
            TWO,
            {'S': [{'E': 1}, {'E': 3}]},
            id='source-projection-of-lists',
        ),
        pytest.param([1, 0], TWO, TREE_TWO, id='indices-order-ignored'),
        pytest.param(
            [0, 0], TWO, {'C': [{'S': [{'E': 1}, {'E': 2}]}]}, id='indices-duplicate'
        ),
        pytest.param([-1], TWO, {}, id='indices-negative'),
        pytest.param([5], TWO, {}, id='indices-out-of-range'),
        pytest.param([1], GAP, {}, id='indices-select-empty'),
    ],
)
def test_mapper_pinned(specs, source, expected):
    """Current behaviour asked about in `OPEN_QUESTIONS.md` (questions 8 to 12).

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


# Polymorphic subsections


class Shape(ArchiveSection):
    """The base section, without annotations: it defers to its subclasses."""

    name = Quantity(type=str)


class Circle(Shape):
    radius = Quantity(type=float)


class Square(Shape):
    side = Quantity(type=float)


class Triangle(Shape):
    height = Quantity(type=float)


class Unrelated(ArchiveSection):
    """A section outside the `Shape` hierarchy with a field named like `Circle`'s."""

    radius = Quantity(type=float)


class Drawing(ArchiveSection):
    title = Quantity(type=str)
    shapes = SubSection(sub_section=Shape, repeats=True)
    first = SubSection(sub_section=Shape, repeats=True)
    second = SubSection(sub_section=Shape, repeats=True)


# Subclasses in definition order, with their one field.
FIELDS = {Circle: 'radius', Square: 'side', Triangle: 'height'}
KINDS = list(FIELDS)
SHAPE_KEYS = ('k1', 'k2')


def annotate(layout: set[tuple[type, str]], update_mode: str | None = None) -> None:
    """(Re)write the annotations: (X, k) in `layout` maps subclass X under key k.

    `Drawing` and its `title` are mapped under every key; a mapped subclass
    reads its section from `.@` and its field from `.<field>`.
    """
    options = {} if update_mode is None else {'update_mode': update_mode}
    Drawing.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = {
        k: MapperAnnotation(mapper='@') for k in SHAPE_KEYS
    }
    Drawing.title.m_annotations[MAPPING_ANNOTATION_KEY] = {
        k: MapperAnnotation(mapper='.title') for k in SHAPE_KEYS
    }
    for kind, field in FIELDS.items():
        keys = [k for x, k in layout if x is kind]
        kind.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = {
            k: MapperAnnotation(mapper='.@', **options) for k in keys
        }
        getattr(kind, field).m_annotations[MAPPING_ANNOTATION_KEY] = {
            k: MapperAnnotation(mapper=f'.{field}') for k in keys
        }


def convert(passes: list[tuple[str, dict]], update_mode: str | None = None) -> Drawing:
    """Convert each (key, source) pass into one `Drawing`, in order."""
    target = MetainfoParser(annotation_key=passes[0][0], data_object=Drawing())
    options = {} if update_mode is None else {'update_mode': update_mode}
    for key, data in passes:
        target.annotation_key = key
        SourceParser(data=deepcopy(data)).convert(target, **options)
    return target.data_object


def summary(sections) -> list[tuple[str, dict[str, Any]]]:
    """Type name and set values of each section, in order."""
    return [
        (type(s).__name__, {k: v for k, v in s.m_to_dict().items() if k != 'm_def'})
        for s in sections or []
    ]


def built(kinds: set[type], data: dict[str, float]) -> list[tuple[str, dict]]:
    """The expected build: annotated kinds with data, in definition order."""
    return [
        (kind.__name__, {FIELDS[kind]: data[FIELDS[kind]]})
        for kind in KINDS
        if kind in kinds and FIELDS[kind] in data
    ]


# Non-zero values only: falsy values empty a section (question 17).
shape_values = st.integers(1, 3).map(float)
shape_data = st.dictionaries(st.sampled_from(sorted(FIELDS.values())), shape_values)
kind_sets = st.sets(st.sampled_from(KINDS))


@given(kind_sets, shape_data)
def test_build_maps_annotated_kinds(kinds, data):
    """summary(shapes) = [(X, {f_X: x[f_X]}) for X in KINDS if X ∈ S and f_X ∈ x].

    The unannotated base defers to every subclass annotated under the active
    key; a subclass is built when its field is in the source, in the
    definition order of the subclasses.
    """
    annotate({(kind, 'k1') for kind in kinds})
    assert summary(convert([('k1', data)]).shapes) == built(kinds, data)


@given(kind_sets, shape_data, st.randoms(use_true_random=False))
def test_build_ignores_source_order(kinds, data, random):
    """M(x) = M(x') for a permutation x' of the keys of `x`: order comes from the schema."""
    annotate({(kind, 'k1') for kind in kinds})
    keys = list(data)
    random.shuffle(keys)
    permuted = {k: data[k] for k in keys}
    first = summary(convert([('k1', data)]).shapes)
    assert summary(convert([('k1', permuted)]).shapes) == first


# Sources with a value for every subclass field.
full_shape_data = st.fixed_dictionaries({f: shape_values for f in FIELDS.values()})


@given(kind_sets, kind_sets, full_shape_data)
def test_append_passes_concatenate(kinds1, kinds2, data):
    """M_k1 then M_k2 with `append` = built(S1, x) ++ built(S2, x) on `shapes`.

    A second pass under another key adds its subclasses after the first
    pass's, so heterogeneous subtypes collect in one list. Every field is in
    the source: an annotated subclass without data in the first pass leaves
    a misaligned element (`test_append_pass_reuses_misaligned_element`).
    """
    annotate(
        {(kind, 'k1') for kind in kinds1} | {(kind, 'k2') for kind in kinds2},
        update_mode='append',
    )
    drawing = convert([('k1', data), ('k2', data)], update_mode='append')
    assert summary(drawing.shapes) == built(kinds1, data) + built(kinds2, data)


def qualified(kind: type) -> str:
    return kind.m_def.qualified_name()


# An element: a subclass with its field, or the base with `name`; or no data.
elements = st.one_of(
    st.tuples(st.sampled_from(KINDS), shape_values),
    st.tuples(st.just(Shape), st.sampled_from(['p', 'q'])),
    st.tuples(st.sampled_from([*KINDS, Shape]), st.none()),
)


@given(st.lists(elements, max_size=5))
def test_from_dict_keeps_type_per_element(items):
    """summary(from_dict(xs)) = [(m_def(x), fields(x)) for x in xs if fields(x)].

    Each element's type comes from its own `m_def`, so one repeating
    subsection holds mixed subtypes in input order; elements without data
    are dropped (question 8).
    """
    field = {**FIELDS, Shape: 'name'}
    source = [
        {'m_def': qualified(kind), **({} if v is None else {field[kind]: v})}
        for kind, v in items
    ]
    target = MetainfoParser(data_object=Drawing())
    target.from_dict({'shapes': source})
    expected = [(kind.__name__, {field[kind]: v}) for kind, v in items if v is not None]
    assert summary(target.data_object.shapes) == expected


def from_dict_shapes(elements: list[dict]) -> list[tuple[str, dict]]:
    target = MetainfoParser(data_object=Drawing())
    target.from_dict({'shapes': elements})
    return summary(target.data_object.shapes)


def test_sibling_subsections_share_subclasses():
    """Every annotated subclass lands in every sibling subsection of the base type.

    No annotation says which subclass belongs to which of `first`, `second`
    (FAIRmat-NFDI/nomad-file-parser#19).
    """
    annotate({(Circle, 'k1'), (Square, 'k1')})
    drawing = convert([('k1', {'radius': 1.0, 'side': 2.0})])
    expected = [('Circle', {'radius': 1.0}), ('Square', {'side': 2.0})]
    assert summary(drawing.first) == expected
    assert summary(drawing.second) == expected


@pytest.mark.parametrize(
    'elements, expected',
    [
        pytest.param(
            [{'m_def': 'no.such.Section', 'name': 'z'}],
            [('Shape', {'name': 'z'})],
            id='unknown-m-def-base-field',
        ),
        pytest.param(
            [{'m_def': 'no.such.Section', 'radius': 1.0}],
            [],
            id='unknown-m-def-subclass-field',
        ),
        pytest.param(
            [{'m_def': qualified(Unrelated), 'radius': 1.0}],
            [],
            id='m-def-outside-hierarchy',
        ),
        pytest.param(
            [{'m_def': qualified(Square), 'radius': 1.0}],
            [],
            id='field-of-other-subclass',
        ),
        pytest.param(
            [{'m_def': qualified(Circle), 'radius': 0.0}, {'name': ''}],
            [],
            id='falsy-only-subsection',
        ),
    ],
)
def test_from_dict_pinned(elements, expected):
    """Current type resolution asked about in `OPEN_QUESTIONS.md` (questions 14, 15, 17)."""
    assert from_dict_shapes(elements) == expected


def test_merge_across_subclasses_keeps_first():
    """Two passes with `merge`, `Circle` under k1 then `Square` under k2, give [Circle].

    The second pass aligns `Square` with the existing `Circle` at position 0;
    the type of the first pass wins and `side` is lost (question 13).
    """
    annotate({(Circle, 'k1'), (Square, 'k2')}, update_mode='merge')
    data = {'radius': 1.0, 'side': 2.0}
    drawing = convert([('k1', data), ('k2', data)], update_mode='merge')
    assert summary(drawing.shapes) == [('Circle', {'radius': 1.0})]


@pytest.mark.parametrize('mode', ['append', 'merge', 'replace'])
def test_scalar_passes_overwrite(mode):
    """A second pass overwrites a scalar under every mode (question 16)."""
    annotate(set())
    drawing = convert([('k1', {'title': 'old'}), ('k2', {'title': 'new'})], mode)
    assert drawing.title == 'new'


@pytest.mark.xfail(strict=True, reason='a later pass reuses a misaligned element')
def test_append_pass_reuses_misaligned_element():
    """Passes k1 (`Circle`, `Triangle`) then k2 (nothing), `append`, on {height: 1}: [Triangle].

    Pass 1 drops the empty `Circle` from the archive but keeps it in the
    parser's intermediate data, so position 0 holds `Circle` there and
    `Triangle` in the archive. Pass 2 replays the data by position, reuses
    the `Triangle` instance at 0 and reassigns its `m_def` to `Circle`: the
    result is [Triangle with `m_def` Circle, Triangle {height: 1}]
    (question 18).
    """
    annotate({(Circle, 'k1'), (Triangle, 'k1')}, update_mode='append')
    data = {'height': 1.0}
    drawing = convert([('k1', data), ('k2', data)], update_mode='append')
    assert [(type(s).__name__, s.m_def.name) for s in drawing.shapes] == [
        ('Triangle', 'Triangle')
    ]
    assert summary(drawing.shapes) == [('Triangle', {'height': 1.0})]
