"""Property-based variant of the polymorphic-resolution regression tests in
``test_mapping_parser.TestPolymorphicSubsectionResolution``.

The exhaustive matrix there checks representative annotation layouts; this
module searches the full generative space (any subset of subclass x key
annotations, any legacy slot value, any key-convert order) and shrinks
failures to a minimal layout.

Properties:
    forall layout, slot, order:  Isolated(k1) ^ Isolated(k2) ^ Unmutated(defs)
"""

from copy import deepcopy

import pytest

# hypothesis is a dev-only extra: skip (not crash) collection where the
# suite runs without the [dev] dependency group installed
pytest.importorskip('hypothesis')

from hypothesis import given  # noqa: E402
from hypothesis import settings as hyp_settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from test_mapping_parser import (
    POLY_KEYS,
    POLY_SUBCLASSES,
    PolyRoot,
    TestPolymorphicSubsectionResolution,
)

from nomad_file_parser.mapping_parser import MAPPING_ANNOTATION_KEY


@given(
    layout=st.frozensets(
        st.tuples(st.sampled_from(sorted(POLY_SUBCLASSES)), st.sampled_from(POLY_KEYS))
    ),
    slot=st.sampled_from([None, 'A', 'B', 'C']),
    order=st.permutations(POLY_KEYS),
)
@hyp_settings(max_examples=200, deadline=None)
def test_annotation_layout_properties(layout, slot, order):
    helper = TestPolymorphicSubsectionResolution
    helper.apply_layout(set(layout))
    if slot is None:
        PolyRoot.settings.more.pop('mapper_m_def', None)
    else:
        PolyRoot.settings.more['mapper_m_def'] = POLY_SUBCLASSES[
            slot
        ].m_def.qualified_name()
    try:
        snapshot = {
            name: (
                deepcopy(cls.m_def.m_annotations.get(MAPPING_ANNOTATION_KEY)),
                PolyRoot.settings.more.get('mapper_m_def'),
            )
            for name, cls in POLY_SUBCLASSES.items()
        }

        for key in order:
            helper.assert_key_resolution(key, set(layout))

        for name, cls in POLY_SUBCLASSES.items():
            annotations, slot_before = snapshot[name]
            assert cls.m_def.m_annotations.get(MAPPING_ANNOTATION_KEY) == annotations
            assert PolyRoot.settings.more.get('mapper_m_def') == slot_before
    finally:
        PolyRoot.settings.more.pop('mapper_m_def', None)
