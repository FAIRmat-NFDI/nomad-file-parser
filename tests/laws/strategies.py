"""Generators of objects and paths, and the wranglers that change the paths.

Not part of the presentation: see `README.md` for what they produce. The
generators build paths as step lists and hand them to the tests as `PathStr`.
"""

from hypothesis import assume
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path

from .paths import PROJECT, Filter, PathStr, Step, Tree, render

# Field names: three, so that sibling objects share keys.
keys = st.sampled_from(['a', 'b', 'c'])
# Leaves, including `None` and the falsy values that must not read as missing.
leaves = st.one_of(st.none(), st.integers(-2, 2), st.booleans(), st.just(''))


def nodes(depth: int) -> st.SearchStrategy[Tree]:
    """Trees nested `depth` levels deep: objects, lists of objects and lists.

    Every container at level `d` holds trees of level `d - 1`; object values
    may also be leaves, so E(obj) contains leaves at every depth, not only at
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


# Objects to read paths from: a non-empty root object of depth 2 to 4.
trees = st.sampled_from([2, 3, 4]).flatmap(
    lambda depth: st.dictionaries(keys, nodes(depth), min_size=1, max_size=3)
)
odds = st.sampled_from([True] * 9 + [False])  # True nine times in ten


@st.composite
def walks(
    draw, project: bool = True, project_first: bool = False
) -> tuple[Tree, list[Step]]:
    """The common generator: an object `obj` and the steps of a path p ∈ E(obj).

    The walk starts at the root and takes, at an object, an existing key
    (preferring one that continues), at a list, an index in range (negative
    ones included) or `[*]` (continuing in one element). It stops at a leaf,
    at an empty container, or with probability 1/10 per step, so
    Path(p).get_data(obj) is not None except where a leaf holds `None`.
    `project=False` never takes `[*]`; `project_first` always takes it at the
    first list.
    """
    obj = draw(trees)
    steps: list[Step] = []
    node: Tree = obj
    while isinstance(node, dict | list) and node and (not steps or draw(odds)):
        if isinstance(node, dict):
            deeper = sorted(
                k for k, v in node.items() if isinstance(v, dict | list) and v
            )
            key = draw(
                st.sampled_from(deeper if deeper and draw(odds) else sorted(node))
            )
            steps.append(key)
            node = node[key]
        elif project and (
            (project_first and PROJECT not in steps) or draw(st.booleans())
        ):
            steps.append(PROJECT)
            node = draw(st.sampled_from(node))
        else:
            index = draw(st.integers(-len(node), len(node) - 1))
            steps.append(index)
            node = node[index]
    return obj, steps


def off_domain(min_index: int = 0) -> st.SearchStrategy[Step]:
    """A step `s` that usually leaves the domain: p.s ∉ E(obj).

    A field from `keys` (missing unless it happens to exist) or an index in
    [min_index, 3] (out of range on short lists; negative if `min_index < 0`).
    """
    return st.one_of(keys, st.integers(min_index, 3))


@st.composite
def perturbed(draw, cases, min_index: int = 0) -> tuple[Tree, list[Step]]:
    """Wrangler: p ↦ p[:i].s.p[i:] with `s` from `off_domain`, in 3/10.

    The path then stops at position `i` (missing key, out-of-range or
    negative index, or a step into a leaf); the tail after `s` is kept, so
    the absorption of the rest is exercised too.
    """
    obj, steps = draw(cases)
    if draw(st.sampled_from([False] * 7 + [True] * 3)):
        at = draw(st.integers(1, len(steps)))
        steps = [*steps[:at], draw(off_domain(min_index)), *steps[at:]]
    return obj, steps


@st.composite
def paths(draw, min_index: int = 0) -> tuple[Tree, PathStr]:
    """An object and a perturbed path on it, one segment."""
    obj, steps = draw(perturbed(walks(), min_index))
    return obj, PathStr.from_steps(steps)


@st.composite
def missing_splits(draw) -> tuple[Tree, tuple[PathStr, PathStr]]:
    """An object `obj` and paths `p`, `q` with `p` ending in an off-domain step.

    p = a[:i].s for a walk `a` and `s` from `off_domain`, and q = a[i:]: so
    p ∉ E(obj) (up to an accidental hit), built rather than filtered.
    """
    obj, steps = draw(walks())
    at = draw(st.integers(1, len(steps)))
    p = [*steps[:at], draw(off_domain())]
    q = steps[at:] or [draw(keys)]
    return obj, (PathStr.from_steps(p), PathStr.from_steps(q))


def is_field(step: Step) -> bool:
    """Whether `step` is a field, i.e. neither an index nor `[*]`."""
    return isinstance(step, str) and step != PROJECT


@st.composite
def splits(
    draw, n: int = 2, head_project: bool = True, tail_field: bool = False
) -> tuple[Tree, tuple[PathStr, ...]]:
    """Wrangler: a perturbed path cut as p1.p2. … .pn, all non-empty.

    `head_project=False` keeps `[*]` out of p1 … p(n-1), so that no projection
    is open at a cut. `tail_field=True` makes p2 … pn start with a field, so
    that each can be written as a relative child `.pi`.
    """
    obj, steps = draw(perturbed(walks()))

    def allowed(i: int) -> bool:
        return (head_project or PROJECT not in steps[:i]) and (
            not tail_field or is_field(steps[i])
        )

    cuts = [i for i in range(1, len(steps)) if allowed(i)]
    assume(len(cuts) >= n - 1)
    chosen = sorted(draw(st.permutations(cuts))[: n - 1])
    bounds = [0, *chosen, len(steps)]
    return obj, tuple(
        PathStr.from_steps(steps[i:j]) for i, j in zip(bounds, bounds[1:])
    )


@st.composite
def at_projection(draw, tail_field: bool = False) -> tuple[Tree, PathStr, PathStr]:
    """Wrangler: a perturbed path split as p0[*].q at its first `[*]`.

    `p0` contains no projection and `q` is non-empty; `tail_field=True` makes
    `q` start with a field, so that it can be written as the child `.q`.
    """
    obj, steps = draw(perturbed(walks(project_first=True)))
    assume(PROJECT in steps)
    i = steps.index(PROJECT)
    assume(i < len(steps) - 1)
    assume(not tail_field or is_field(steps[i + 1]))
    return obj, PathStr.from_steps(steps[:i]), PathStr.from_steps(steps[i + 1 :])


@st.composite
def pipelines(draw, min_index: int = 0) -> tuple[Tree, PathStr]:
    """Wrangler: a perturbed path cut into segments p1 | … | pm, m ≤ 3.

    `min_index < 0` lets the perturbation insert negative indices.
    """
    obj, steps = draw(perturbed(walks(), min_index))
    cuts = draw(st.sets(st.integers(1, len(steps)), max_size=2))
    bounds = [0, *sorted(cuts), len(steps)]
    segments = [steps[i:j] for i, j in zip(bounds, bounds[1:]) if steps[i:j]]
    return obj, PathStr.from_steps(*segments)


@st.composite
def malformed(draw) -> tuple[Tree, str]:
    """Wrangler: a perturbed path rendered as `p..k`, a plain `str` that does not parse."""
    obj, steps = draw(perturbed(walks()))
    return obj, f'{render(steps)}..{draw(keys)}'


@st.composite
def at_filter(draw) -> tuple[Tree, PathStr, Filter, list[Step]]:
    """Wrangler: a perturbed walk cut as p0[?k==v].q at its first `[*]`, which becomes a filter.

    `p0` opens no projection; `q` may be empty. In half the cases the key and
    value come from an element of the list at `p0`, so that the filter
    matches some elements; otherwise they are drawn freely.
    """
    obj, steps = draw(perturbed(walks(project_first=True)))
    assume(PROJECT in steps)
    i = steps.index(PROJECT)
    p0 = PathStr.from_steps(steps[:i])
    elements = Path(path=p0).get_data(obj)
    pairs = sorted(
        {
            (k, v)
            for e in (elements if isinstance(elements, list) else [])
            if isinstance(e, dict)
            for k, v in e.items()
            if not isinstance(v, dict | list)
        },
        key=repr,
    )
    if pairs and draw(st.booleans()):
        key, value = draw(st.sampled_from(pairs))
    else:
        key, value = draw(keys), draw(leaves)
    return obj, p0, Filter(key, value), steps[i + 1 :]
