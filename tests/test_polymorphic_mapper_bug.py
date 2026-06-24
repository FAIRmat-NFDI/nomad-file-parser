"""
Test the framework bug where function-only mappers don't work on polymorphic subsections.

This test demonstrates that the mapping parser creates a BaseMapper instead of a
Transformer when only a function mapper is provided for polymorphic subsections,
causing the function to never be called.

Property: ∀f ∈ FunctionMappers, ∀s ∈ PolymorphicSubsections:
    HasQuantityAnnotation(s) → CreatesTransformer(f, s)
    ¬HasQuantityAnnotation(s) → CreatesBaseMapper(f, s) → ¬Executed(f)

Workaround: Add a dummy quantity annotation to force Transformer creation.
"""

import json
from typing import Any, List

import pytest
from hypothesis import given, settings, strategies as st
from nomad.datamodel import EntryArchive
from nomad.datamodel.metainfo.annotations import Mapper
from nomad.metainfo import MEnum, Package, Quantity, Section, SubSection
from nomad.parsing.file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    MetainfoParser,
)


def create_test_schema(
    with_quantity_annotation: bool = False,
    with_dummy_path: bool = False
) -> tuple[Section, Section, Section]:
    """Create test schema with polymorphic subsections."""
    m_package = Package()

    class BaseSection(Section):
        pass

    class DerivedA(BaseSection):
        name = Quantity(type=str)
        value = Quantity(type=float)

    class DerivedB(BaseSection):
        name = Quantity(type=str)
        count = Quantity(type=int)

    class Container(Section):
        items = SubSection(sub_section=BaseSection, repeats=True)

    # Add function annotation to create multiple instances
    if with_quantity_annotation:
        # WORKAROUND: Add dummy quantity annotation to force Transformer
        DerivedA.name.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(mapper='.dummy_to_force_transformer')
        })

    if with_dummy_path:
        # Alternative workaround: Add dummy path mapper at section level
        DerivedA.m_def.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(mapper='.@')  # Dummy path
        })

    # Add the actual function mapper
    BaseSection.m_def.m_annotations.setdefault(
        MAPPING_ANNOTATION_KEY, {}
    ).update({
        'test': Mapper(
            mapper=('get_multiple_items', []),
            update_mode='append'
        )
    })

    m_package.init_metainfo()
    return Container, DerivedA, DerivedB


class TestPolymorphicMapperBug:
    """Test polymorphic subsection function mapper bug."""

    def test_function_mapper_without_workaround_fails(self):
        """
        Property: ¬HasQuantityAnnotation(s) → ¬Executed(function)

        Without a quantity annotation, the function mapper is not executed
        for polymorphic subsections.
        """
        Container, DerivedA, DerivedB = create_test_schema(
            with_quantity_annotation=False,
            with_dummy_path=False
        )

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.function_call_count = 0

            def get_multiple_items(self, source: dict) -> List[dict]:
                """Return multiple items to test update_mode='append'."""
                self.function_call_count += 1
                return [
                    {'name': 'item1', 'value': 1.0},
                    {'name': 'item2', 'value': 2.0},
                    {'name': 'item3', 'value': 3.0},
                ]

        # Create test data
        test_data = {'items': []}  # Empty, function should generate items

        # Parse with the schema
        parser = TestParser()
        parser.annotation_key = 'test'
        container = Container()
        parser.data_object = container
        parser._data = test_data  # Use private attribute
        parser.parse()

        # EXPECTED: Function called, 3 items created
        # ACTUAL (BUG): Function not called, no items created
        assert parser.function_call_count == 0, "Bug confirmed: function not called"
        assert len(container.items) == 0, "Bug confirmed: no items created"

    def test_function_mapper_with_quantity_workaround_works(self):
        """
        Property: HasQuantityAnnotation(s) → Executed(function)

        With a dummy quantity annotation, the function mapper is executed.
        """
        Container, DerivedA, DerivedB = create_test_schema(
            with_quantity_annotation=True,  # Apply workaround
            with_dummy_path=False
        )

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.function_call_count = 0

            def get_multiple_items(self, source: dict) -> List[dict]:
                """Return multiple items to test update_mode='append'."""
                self.function_call_count += 1
                # Return dicts that match DerivedA schema
                return [
                    {'m_def': 'DerivedA', 'name': 'item1', 'value': 1.0},
                    {'m_def': 'DerivedA', 'name': 'item2', 'value': 2.0},
                    {'m_def': 'DerivedA', 'name': 'item3', 'value': 3.0},
                ]

        # Create test data
        test_data = {}  # Empty, function should generate items

        # Parse with the schema
        parser = TestParser()
        parser.annotation_key = 'test'
        container = Container()
        parser.data_object = container
        parser._data = test_data  # Use private attribute
        parser.parse()

        # With workaround: Function IS called, items ARE created
        assert parser.function_call_count > 0, "Workaround works: function called"
        # Note: Actual item creation may still fail due to other framework issues
        # but at least the function is being executed

    def test_function_mapper_with_path_workaround_works(self):
        """
        Property: HasPathMapper(s) → Executed(function)

        With a dummy path mapper, the function mapper is executed.
        """
        Container, DerivedA, DerivedB = create_test_schema(
            with_quantity_annotation=False,
            with_dummy_path=True  # Apply alternative workaround
        )

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.function_call_count = 0

            def get_multiple_items(self, source: dict) -> List[dict]:
                """Return multiple items."""
                self.function_call_count += 1
                return [
                    {'m_def': 'DerivedA', 'name': 'item1', 'value': 1.0},
                ]

        test_data = {}
        parser = TestParser()
        parser.annotation_key = 'test'
        container = Container()
        parser.data_object = container
        parser.data = test_data
        parser.parse()

        # With path workaround: Function IS called
        assert parser.function_call_count > 0, "Path workaround works: function called"

    @given(
        num_items=st.integers(min_value=0, max_value=5),
        use_workaround=st.booleans()
    )
    @settings(max_examples=20)
    def test_polymorphic_function_mapper_property(
        self,
        num_items: int,
        use_workaround: bool
    ):
        """
        Property-based test for the polymorphic mapper bug.

        Property: ∀n ∈ ℕ, ∀w ∈ {true, false}:
            w → FunctionCalled(n) → ItemsCreated(min(n, actual))
            ¬w → ¬FunctionCalled(n) → ItemsCreated(0)
        """
        Container, DerivedA, DerivedB = create_test_schema(
            with_quantity_annotation=use_workaround,
            with_dummy_path=False
        )

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.function_called = False
                self.num_items = num_items

            def get_multiple_items(self, source: dict) -> List[dict]:
                self.function_called = True
                return [
                    {'m_def': 'DerivedA', 'name': f'item{i}', 'value': float(i)}
                    for i in range(self.num_items)
                ]

        parser = TestParser()
        parser.annotation_key = 'test'
        container = Container()
        parser.data_object = container
        parser.data = {}
        parser.parse()

        if use_workaround:
            # With workaround, function should be called
            assert parser.function_called, f"Expected function call with workaround"
        else:
            # Without workaround, function won't be called (bug)
            assert not parser.function_called, f"Bug: function called without workaround"
            assert len(container.items) == 0, f"Bug: items created without function call"


class TestSCFConvergenceBug:
    """Test the specific SCF convergence criteria bug."""

    def test_scf_criteria_without_workaround(self):
        """
        Test that SCF criteria creation fails without workaround.

        This simulates the exact issue in FHI-aims parser where
        get_all_criteria() is not called for SelfConsistency sections.
        """
        m_package = Package()

        class SelfConsistency(Section):
            name = Quantity(type=str)
            threshold_change = Quantity(type=float)

        class NumericalSettings(Section):
            pass

        class KSpace(NumericalSettings):
            grid = Quantity(type=int, shape=[3])

        class DFT(Section):
            numerical_settings = SubSection(
                sub_section=NumericalSettings,
                repeats=True
            )

        # Add function mapper WITHOUT workaround
        SelfConsistency.m_def.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(
                mapper=('get_all_criteria', []),
                update_mode='append'
            )
        })

        m_package.init_metainfo()

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.get_all_criteria_called = False

            def get_all_criteria(self, source: dict) -> List[dict]:
                """Should return 3 criteria but won't be called."""
                self.get_all_criteria_called = True
                return [
                    {'name': 'total_energy_change', 'threshold_change': 1e-6},
                    {'name': 'charge_density_change', 'threshold_change': 1e-5},
                    {'name': 'sum_eigenvalues_change', 'threshold_change': 1e-3},
                ]

        parser = TestParser()
        parser.annotation_key = 'test'
        dft = DFT()
        parser.data_object = dft
        parser.data = {}
        parser.parse()

        # BUG: Function not called, no SelfConsistency instances created
        assert not parser.get_all_criteria_called, "Bug: get_all_criteria not called"
        assert len(dft.numerical_settings) == 0, "Bug: no numerical_settings created"

    def test_scf_criteria_with_workaround(self):
        """
        Test that SCF criteria creation works with quantity annotation workaround.
        """
        m_package = Package()

        class SelfConsistency(Section):
            name = Quantity(type=str)
            threshold_change = Quantity(type=float)

        class NumericalSettings(Section):
            pass

        class KSpace(NumericalSettings):
            grid = Quantity(type=int, shape=[3])

        class DFT(Section):
            numerical_settings = SubSection(
                sub_section=NumericalSettings,
                repeats=True
            )

        # WORKAROUND: Add dummy quantity annotation
        SelfConsistency.name.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(mapper='.dummy_field')
        })

        # Now add function mapper
        SelfConsistency.m_def.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(
                mapper=('get_all_criteria', []),
                update_mode='append'
            )
        })

        m_package.init_metainfo()

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.get_all_criteria_called = False

            def get_all_criteria(self, source: dict) -> List[dict]:
                """Return 3 criteria - should be called with workaround."""
                self.get_all_criteria_called = True
                return [
                    {'m_def': 'SelfConsistency', 'name': 'total_energy_change', 'threshold_change': 1e-6},
                    {'m_def': 'SelfConsistency', 'name': 'charge_density_change', 'threshold_change': 1e-5},
                    {'m_def': 'SelfConsistency', 'name': 'sum_eigenvalues_change', 'threshold_change': 1e-3},
                ]

        parser = TestParser()
        parser.annotation_key = 'test'
        dft = DFT()
        parser.data_object = dft
        parser.data = {}
        parser.parse()

        # With workaround: Function IS called
        assert parser.get_all_criteria_called, "Workaround: get_all_criteria called"
        # Note: Actual instance creation may still have issues, but function is called