"""The `Shape` hierarchy under `Drawing`, and how the laws annotate and convert it."""

from copy import deepcopy
from typing import Any

from hypothesis import strategies as st
from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import Mapper as MapperAnnotation
from nomad.metainfo import Quantity, SubSection

from nomad_file_parser.mapping_parser import MAPPING_ANNOTATION_KEY, MetainfoParser

from .reference import SourceParser


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


# Sources with a value for every subclass field.
full_shape_data = st.fixed_dictionaries({f: shape_values for f in FIELDS.values()})


def qualified(kind: type) -> str:
    return kind.m_def.qualified_name()


# An element: a subclass with its field, or the base with `name`; or no data.
elements = st.one_of(
    st.tuples(st.sampled_from(KINDS), shape_values),
    st.tuples(st.just(Shape), st.sampled_from(['p', 'q'])),
    st.tuples(st.sampled_from([*KINDS, Shape]), st.none()),
)


def from_dict_shapes(elements: list[dict]) -> list[tuple[str, dict]]:
    target = MetainfoParser(data_object=Drawing())
    target.from_dict({'shapes': elements})
    return summary(target.data_object.shapes)
