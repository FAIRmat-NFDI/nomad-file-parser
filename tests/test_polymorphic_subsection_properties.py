"""
Regression tests for polymorphic sub-section resolution after the removal of
the ``mapper_m_def`` slot read (the cross-parser poisoning mechanism).

Key predicates:
- ResolvedUnder(section, key): section's subclass mapper is applied when
  converting with annotation_key=key
- Isolated(key): ResolvedUnder(S, key) depends only on key's own annotations
- Unmutated(defs): converting never changes schema definitions

Properties under test:
    ∀ layout, slot, order:  Isolated(k1) ∧ Isolated(k2) ∧ Unmutated(defs)

The legacy slot (``Section.more['mapper_m_def']``, written by old parser
plugins) must be inert: it must neither redirect resolution of a foreign
annotation key nor be consumed (the old reader popped it, which made results
depend on which parser built its mappers first).
"""

from copy import deepcopy
from typing import Any

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from nomad.datamodel import ArchiveSection
from nomad.datamodel.metainfo.annotations import Mapper as MapperAnnotation
from nomad.metainfo import Quantity, SubSection

from nomad_file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    MappingParser,
    MetainfoParser,
)


class PolySettings(ArchiveSection):
    name = Quantity(type=str)


class PolyA(PolySettings):
    alpha = Quantity(type=float)


class PolyB(PolySettings):
    beta = Quantity(type=float)


class PolyC(PolySettings):
    gamma = Quantity(type=float)


class PolyRoot(ArchiveSection):
    settings = SubSection(sub_section=PolySettings, repeats=True)


PolyRoot.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = dict(
    k1=MapperAnnotation(mapper='@'), k2=MapperAnnotation(mapper='@')
)

SUBCLASSES = {'A': PolyA, 'B': PolyB, 'C': PolyC}
FIELD = {'A': 'alpha', 'B': 'beta', 'C': 'gamma'}
KEYS = ('k1', 'k2')
SOURCE = {'alpha': 1.0, 'beta': 2.0, 'gamma': 3.0}


class DictParser(MappingParser):
    def from_dict(self, dct: dict[str, Any]):
        return super().from_dict(dct)

    def load_file(self) -> Any:
        return super().load_file()

    def to_dict(self, **kwargs) -> dict[str | int, Any]:
        return super().to_dict(**kwargs)


def apply_layout(layout: set[tuple[str, str]]) -> None:
    """(Re)write the fixture's annotations: entry (X, k) fully annotates
    subclass X (section + its quantity) under key k; everything else bare."""
    for cls_name, cls in SUBCLASSES.items():
        section_anns = {
            k: MapperAnnotation(mapper='.@')
            for x, k in layout
            if x == cls_name
        }
        quantity_anns = {
            k: MapperAnnotation(mapper=f'.{FIELD[cls_name]}')
            for x, k in layout
            if x == cls_name
        }
        cls.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = section_anns
        quantity = getattr(cls, FIELD[cls_name])
        quantity.m_annotations[MAPPING_ANNOTATION_KEY] = quantity_anns


def convert_under(key: str) -> list:
    target = MetainfoParser(annotation_key=key, data_object=PolyRoot())
    DictParser(data=deepcopy(SOURCE)).convert(target)
    return list(target.data_object.settings or [])


def assert_key_resolution(key: str, layout: set[tuple[str, str]]) -> None:
    built = convert_under(key)
    expected = sorted(x for x, k in layout if k == key)
    assert sorted(type(s).__name__[-1] for s in built) == expected
    for section in built:
        field = FIELD[type(section).__name__[-1]]
        assert getattr(section, field) == SOURCE[field]


def test_polymorphic_scan_resolves_per_key():
    """The d1df594 feature's intent without the slot: the inheriting-section
    scan picks exactly the subclasses annotated under the active key."""
    apply_layout({('A', 'k1'), ('B', 'k2')})
    PolyRoot.settings.more.pop('mapper_m_def', None)

    assert_key_resolution('k1', {('A', 'k1')})
    assert_key_resolution('k2', {('B', 'k2')})


def test_legacy_slot_is_inert_and_unmutated():
    """A slot left by an un-migrated writer must not hijack a foreign key's
    resolution, and must survive the mapper build (the old reader popped it,
    poisoning whichever parser built first)."""
    apply_layout({('A', 'k1'), ('B', 'k2')})
    slot_value = PolyA.m_def.qualified_name()
    PolyRoot.settings.more['mapper_m_def'] = slot_value
    try:
        assert_key_resolution('k2', {('B', 'k2')})
        assert PolyRoot.settings.more.get('mapper_m_def') == slot_value
        assert_key_resolution('k1', {('A', 'k1')})
        assert PolyRoot.settings.more.get('mapper_m_def') == slot_value
    finally:
        PolyRoot.settings.more.pop('mapper_m_def', None)


@given(
    layout=st.frozensets(
        st.tuples(st.sampled_from(sorted(SUBCLASSES)), st.sampled_from(KEYS))
    ),
    slot=st.sampled_from([None, 'A', 'B', 'C']),
    order=st.permutations(KEYS),
)
@hyp_settings(max_examples=75, deadline=None)
def test_annotation_layout_properties(layout, slot, order):
    """∀ layout, slot, order: Isolated(k1) ∧ Isolated(k2) ∧ Unmutated(defs)."""
    apply_layout(set(layout))
    if slot is None:
        PolyRoot.settings.more.pop('mapper_m_def', None)
    else:
        PolyRoot.settings.more['mapper_m_def'] = SUBCLASSES[
            slot
        ].m_def.qualified_name()
    try:
        snapshot = {
            name: (
                deepcopy(cls.m_def.m_annotations.get(MAPPING_ANNOTATION_KEY)),
                PolyRoot.settings.more.get('mapper_m_def'),
            )
            for name, cls in SUBCLASSES.items()
        }

        for key in order:
            assert_key_resolution(key, set(layout))

        for name, cls in SUBCLASSES.items():
            anns, slot_before = snapshot[name]
            assert cls.m_def.m_annotations.get(MAPPING_ANNOTATION_KEY) == anns
            assert PolyRoot.settings.more.get('mapper_m_def') == slot_before
    finally:
        PolyRoot.settings.more.pop('mapper_m_def', None)
