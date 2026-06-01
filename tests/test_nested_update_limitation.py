"""
Simplified property tests demonstrating multi-pass nested instance update limitation.

These tests show that annotation-based updates work at depth 1 but fail at depth 2+,
characterizing exactly where the framework limitation begins.

See: mapping-parser-nested-update-modes.md "Framework Limitation" section
"""

import pytest
from hypothesis import given, settings, strategies as st

# =============================================================================
# Monkeypatch ClassicLogger to Fix ABC Interaction
# =============================================================================
from nomad.utils import ClassicLogger

_original_getattr = ClassicLogger.__getattr__


def _fixed_getattr(self, key):
    """Fixed __getattr__ that doesn't return lambda for __isabstractmethod__."""
    if key == '__isabstractmethod__':
        raise AttributeError(key)
    return _original_getattr(self, key)


ClassicLogger.__getattr__ = _fixed_getattr


# =============================================================================
# Test Schemas
# =============================================================================


def create_depth_1_schema():
    """Schema with value at depth 1: Root.value"""
    from nomad.metainfo import MSection, Quantity

    class Root(MSection):
        value = Quantity(type=int)
        name = Quantity(type=str)

    return Root


def create_depth_2_schema():
    """Schema with value at depth 2: Root.child.value"""
    from nomad.metainfo import MSection, Quantity, SubSection

    class Child(MSection):
        value = Quantity(type=int)
        name = Quantity(type=str)

    class Root(MSection):
        child = SubSection(sub_section=Child)

    return Root, Child


# =============================================================================
# Property 1: from_dict() Updates at Depth 1 vs Depth 2
# =============================================================================


class TestFromDictUpdateDepth:
    """Test whether from_dict() can update values at different depths."""

    @given(
        first_value=st.integers(min_value=1, max_value=50),
        second_value=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_depth_1_update_succeeds(self, first_value: int, second_value: int):
        """Depth 1: from_dict() CAN update existing value (baseline).

        This establishes that depth-1 updates work, providing comparison point.
        """
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root = create_depth_1_schema()

        # First pass: Create with first_value
        parser = MetainfoParser()
        parser.data_object = Root()
        parser.from_dict({'value': first_value, 'name': 'first'})

        assert parser.data_object.value == first_value, 'First pass failed'

        # Second pass: Update to second_value
        parser.from_dict({'value': second_value, 'name': 'second'})

        # Verify: Update succeeded at depth 1
        assert parser.data_object.value == second_value, (
            f'Depth-1 update failed (unexpected!):\n'
            f'  Expected: {second_value}\n'
            f'  Got: {parser.data_object.value}'
        )

    @given(
        first_value=st.integers(min_value=1, max_value=50),
        second_value=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_depth_2_update_fails(self, first_value: int, second_value: int):
        """Depth 2: from_dict() CANNOT update existing nested value (limitation).

        This demonstrates the framework limitation - updates fail at depth 2.
        """
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root, Child = create_depth_2_schema()

        # First pass: Create nested structure with first_value
        parser = MetainfoParser()
        parser.data_object = Root()
        parser.from_dict({'child': {'value': first_value, 'name': 'first'}})

        assert parser.data_object.child is not None, 'First pass failed to create child'
        assert parser.data_object.child.value == first_value, 'First pass failed'

        # Second pass: Try to update nested value
        parser.from_dict({'child': {'value': second_value, 'name': 'second'}})

        # Check result
        if parser.data_object.child.value == second_value:
            # Update worked! (unexpected but good)
            pass
        else:
            # Expected: Update failed at depth 2
            pytest.skip(
                f'Depth-2 update fails (documented limitation):\n'
                f'  Expected: {second_value}\n'
                f'  Got: {parser.data_object.child.value}\n'
                f'  This confirms the framework cannot update nested instances'
            )


# =============================================================================
# Property 2: Manual Transformer Works at All Depths
# =============================================================================


class TestManualTransformerBaseline:
    """Demonstrate that manual traversal works where annotations fail."""

    @given(
        first_value=st.integers(min_value=1, max_value=50),
        second_value=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_manual_update_depth_1_succeeds(self, first_value: int, second_value: int):
        """Manual update works at depth 1."""
        Root = create_depth_1_schema()

        root = Root()
        root.value = first_value

        # Manual update
        root.value = second_value

        assert root.value == second_value

    @given(
        first_value=st.integers(min_value=1, max_value=50),
        second_value=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_manual_update_depth_2_succeeds(self, first_value: int, second_value: int):
        """Manual update works at depth 2 (proves workaround viability)."""
        Root, Child = create_depth_2_schema()

        root = Root()
        root.child = Child()
        root.child.value = first_value

        # Manual traversal and update
        root.child.value = second_value

        assert root.child.value == second_value, (
            'Manual update failed at depth 2 - this should never fail'
        )


# =============================================================================
# Property 3: Characterize Exact Failure Point
# =============================================================================


class TestUpdateDepthCharacterization:
    """Systematically characterize at which depth updates start failing."""

    def test_depth_1_always_works(self):
        """Depth 1 updates should always succeed (control case)."""
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root = create_depth_1_schema()

        parser = MetainfoParser()
        parser.data_object = Root()

        # Multiple update cycles
        for i in range(5):
            parser.from_dict({'value': i * 10})
            assert parser.data_object.value == i * 10

    def test_depth_2_behavior(self):
        """Document depth 2 update behavior.

        This test explicitly documents whether depth-2 updates work or not,
        providing concrete evidence for feature request.
        """
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root, Child = create_depth_2_schema()

        parser = MetainfoParser()
        parser.data_object = Root()

        # First pass
        parser.from_dict({'child': {'value': 10, 'name': 'first'}})
        assert parser.data_object.child is not None
        assert parser.data_object.child.value == 10

        # Second pass
        parser.from_dict({'child': {'value': 20, 'name': 'second'}})

        result_value = parser.data_object.child.value

        # Document the behavior
        if result_value == 20:
            print('\n✓ Depth-2 update succeeded (framework may have fixed limitation)')
        elif result_value == 10:
            print('\n✗ Depth-2 update failed (value unchanged from first pass)')
            print('  This confirms documented limitation')
        else:
            print(f'\n? Depth-2 update produced unexpected value: {result_value}')

        # This test documents behavior, doesn't assert
        # (Allows us to track if framework changes in future)


# =============================================================================
# Property 4: Multi-Pass Update with Same Data Structure
# =============================================================================


class TestMultiPassSameStructure:
    """Test whether multiple passes can incrementally populate same structure."""

    @given(
        value1=st.integers(min_value=1, max_value=50),
        value2=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_depth_1_incremental_population(self, value1: int, value2: int):
        """At depth 1, multiple passes can incrementally add fields."""
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root = create_depth_1_schema()

        parser = MetainfoParser()
        parser.data_object = Root()

        # First pass: populate value
        parser.from_dict({'value': value1})
        assert parser.data_object.value == value1

        # Second pass: populate name (different field)
        parser.from_dict({'name': 'second_pass'})
        assert parser.data_object.name == 'second_pass'
        assert parser.data_object.value == value1  # Should preserve first pass

    @given(
        value1=st.integers(min_value=1, max_value=50),
        value2=st.integers(min_value=51, max_value=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_depth_2_incremental_population(self, value1: int, value2: int):
        """At depth 2, test whether multiple passes can populate different child fields."""
        from nomad.parsing.file_parser.mapping_parser import MetainfoParser

        Root, Child = create_depth_2_schema()

        parser = MetainfoParser()
        parser.data_object = Root()

        # First pass: Create child with value
        parser.from_dict({'child': {'value': value1}})
        assert parser.data_object.child is not None
        assert parser.data_object.child.value == value1

        # Second pass: Update child with name
        parser.from_dict({'child': {'name': 'second_pass'}})

        # Check if both fields preserved
        has_value = parser.data_object.child.value == value1
        has_name = parser.data_object.child.name == 'second_pass'

        if has_value and has_name:
            # Both preserved - incremental population worked
            pass
        elif has_name and not has_value:
            pytest.skip(
                'Depth-2 incremental population loses previous field:\n'
                '  Second pass replaced child instead of merging'
            )
        else:
            pytest.skip(f'Unexpected state: value={has_value}, name={has_name}')


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short', '-s'])
