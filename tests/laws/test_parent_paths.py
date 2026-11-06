"""Relative paths: a child `.q` under a parent path `p`."""

from hypothesis import given

from nomad_file_parser.mapping_parser import Path

from .paths import PathStr
from .strategies import at_projection, pipelines, splits, trees


def inherit(parent: PathStr, child: PathStr) -> Path:
    """The `Path` of the child `.child` under `parent`."""
    return Path(path=child.relative(), parent=Path(path=parent))


@given(splits(head_project=False, tail_field=True))
def test_prefix_equals_reroot(case):
    """.q under p: absolute path p.q, and Path(p.q).get_data(obj) = Path(q).get_data(Path(p).get_data(obj)).

    For `p` opening no projection. Prepending (static) and re-rooting
    (runtime) agree: removing the prefix `p` moves the root down to
    Path(p).get_data(obj).
    """
    obj, (parent, child) = case
    child_path = inherit(parent, child)
    assert child_path.absolute_path == parent.dot(child)
    rerooted = Path(path=child_path.relative_path).get_data(
        Path(path=parent).get_data(obj)
    )
    assert Path(path=child_path.absolute_path).get_data(obj) == rerooted


@given(at_projection(tail_field=True))
def test_projecting_parent_maps_child(case):
    """.q under p0[*]: Path(p0[*].q).get_data(obj) = [r for o in Path(p0).get_data(obj) if (r := Path(q).get_data(o)) is not None].

    For `p0` opening no projection. A projecting parent applies its child per
    element, which is what the mapper does when a section's source resolves
    to a list.
    """
    obj, p0, child = case
    assert not p0.opens_projection()  # ensured by the generator
    child_path = inherit(p0.dot('[*]'), child)
    base = Path(path=p0).get_data(obj)
    mapped = None
    if isinstance(base, list):
        child = Path(path=child_path.relative_path)
        mapped = [r for o in base if (r := child.get_data(o)) is not None]
    assert Path(path=child_path.absolute_path).get_data(obj) == mapped


@given(splits(n=3, head_project=False, tail_field=True))
def test_parent_chain_is_associative(case):
    """.r under .q under p: absolute path p.q.r, and Path(p.q.r).get_data(obj) = Path(r).get_data(Path(q).get_data(Path(p).get_data(obj))).

    Prepending along a chain of parents is associative and agrees with
    re-rooting step by step, for parents opening no projection.
    """
    obj, (grandparent, parent, child) = case
    child_path = Path(
        path=child.relative(),
        parent=Path(path=parent.relative(), parent=Path(path=grandparent)),
    )
    assert child_path.absolute_path == grandparent.dot(parent).dot(child)
    stepwise = Path(path=child).get_data(
        Path(path=parent).get_data(Path(path=grandparent).get_data(obj))
    )
    assert Path(path=child_path.absolute_path).get_data(obj) == stepwise


@given(pipelines())
def test_prefix_is_dropped(case):
    """Path(.p).get_data(obj) = Path(p).get_data(obj): on its own, the leading `.` only marks `p` as relative."""
    obj, path = case
    assert Path(path=path.relative()).get_data(obj) == Path(path=path).get_data(obj)


@given(trees)
def test_relative_at_is_current(obj):
    """Path(.@).get_data(obj) = obj: `.@` is the relative spelling of the current node."""
    assert Path(path=PathStr('@').relative()).get_data(obj) == obj
