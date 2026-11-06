"""Relative paths: a child `.q` under a parent path `p`."""

from hypothesis import given

from nomad_file_parser.mapping_parser import Path

from .reference import get
from .strategies import (
    PROJECT,
    Step,
    at_projection,
    pipelines,
    render,
    render_pipeline,
    splits,
)


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


@given(pipelines())
def test_prefix_is_dropped(case):
    """eval(.p) = eval(p): on its own, the leading `.` only marks `p` as relative."""
    source, pipeline = case
    path = render_pipeline(pipeline)
    assert get('.' + path, source) == get(path, source)
