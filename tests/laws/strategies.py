"""Generators of sources and paths, and the wranglers that change them.

Not part of the presentation: see `README.md` for what they produce.
"""

from typing import Any

from hypothesis import assume
from hypothesis import strategies as st

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
