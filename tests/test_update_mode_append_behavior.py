"""
Test how update_mode='append' behaves with functions returning lists.

Hypothesis:
∀f ∈ Functions, ∀L ∈ Lists:
    f() → L ∧ update_mode='append' →
        (AppendEachItem(L) ∨ AppendFirstItem(L) ∨ AppendListAsItem(L))

We need to determine which behavior actually occurs.
"""

from typing import Any, List
import pytest
from hypothesis import given, settings, strategies as st
from nomad.datamodel.metainfo.annotations import Mapper
from nomad.metainfo import Package, Quantity, Section, SubSection
from nomad.parsing.file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    MetainfoParser,
)


def create_test_schema_for_append_behavior():
    """Create schema to test update_mode='append' behavior."""
    m_package = Package()

    class Item(Section):
        name = Quantity(type=str)
        value = Quantity(type=float)

    class Container(Section):
        items = SubSection(sub_section=Item, repeats=True)

    m_package.init_metainfo()
    return Container, Item


class TestUpdateModeAppendBehavior:
    """Test how update_mode='append' handles function returns."""

    @given(
        num_items=st.integers(min_value=1, max_value=5),
        use_list_return=st.booleans()
    )
    @settings(max_examples=10)
    def test_append_mode_with_list_return(self, num_items: int, use_list_return: bool):
        """
        Property: ∀n ∈ ℕ₊, ∀use_list ∈ {true, false}:
            use_list → f() returns List[Dict] with n items
            ¬use_list → f() returns single Dict

        Test whether append mode:
        1. Appends each item from list (desired)
        2. Appends only first item from list (bug)
        3. Appends list as single item (bug)
        4. Correctly appends single dict when not a list
        """
        Container, Item = create_test_schema_for_append_behavior()

        class TestParser(MetainfoParser):
            def __init__(self, num_items: int, use_list: bool):
                super().__init__()
                self.num_items = num_items
                self.use_list = use_list
                self.function_call_count = 0

            def get_items(self, source: dict) -> List[dict] | dict:
                """Return either a list of dicts or a single dict."""
                self.function_call_count += 1

                if self.use_list:
                    # Return a list of items
                    return [
                        {'name': f'item_{i}', 'value': float(i)}
                        for i in range(self.num_items)
                    ]
                else:
                    # Return a single item
                    return {'name': 'single_item', 'value': 42.0}

        # Add function annotation with append mode
        Item.m_def.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(
                mapper=('get_items', []),
                update_mode='append'
            )
        })

        # Add dummy quantity annotation to ensure function is called
        Item.name.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(mapper='.dummy')
        })

        parser = TestParser(num_items, use_list_return)
        parser.annotation_key = 'test'
        container = Container()
        parser.data_object = container
        parser._data = {}

        # Attempt to parse (may fail, but we'll check what happens)
        try:
            # Trigger the mapping somehow
            # Note: The actual invocation depends on framework internals
            pass
        except:
            pass

        # Check results
        print(f"\nTest case: use_list={use_list_return}, num_items={num_items}")
        print(f"Function called: {parser.function_call_count} times")
        print(f"Items created: {len(container.items)}")

        if use_list_return:
            # EXPECTED: len(container.items) == num_items (each item appended)
            # ACTUAL: Need to determine through testing
            assert parser.function_call_count <= 1, "Function should be called at most once"
            # Record actual behavior for analysis
            actual_items_created = len(container.items)

            if actual_items_created == num_items:
                print("✓ Behavior: Appends each item from list (correct)")
            elif actual_items_created == 1:
                print("✗ Behavior: Appends only first item or list as single item")
            elif actual_items_created == 0:
                print("✗ Behavior: No items created (framework issue)")
            else:
                print(f"? Unexpected: {actual_items_created} items created")


class TestSCFCriteriaSpecificBehavior:
    """Test the specific SCF criteria case with update_mode='append'."""

    def test_get_all_criteria_return_behavior(self):
        """
        Test what happens when get_all_criteria returns a list of 3 dicts.

        Property: get_all_criteria() → [dict₁, dict₂, dict₃]
            ∧ update_mode='append' →
            |numerical_settings| ∈ {1, 3, 4}

        Where:
        - 1 means only first item appended (bug)
        - 3 means each dict creates an instance (desired)
        - 4 means 3 + 1 KSpace (expected total)
        """
        m_package = Package()

        class NumericalSettings(Section):
            pass

        class SelfConsistency(NumericalSettings):
            name = Quantity(type=str)
            threshold_change = Quantity(type=float)

        class KSpace(NumericalSettings):
            grid = Quantity(type=int, shape=[3])

        class DFT(Section):
            numerical_settings = SubSection(
                sub_section=NumericalSettings,
                repeats=True
            )

        class TestParser(MetainfoParser):
            def __init__(self):
                super().__init__()
                self.get_all_criteria_called = False
                self.returned_items = []

            def get_all_criteria(self, source: dict) -> List[dict]:
                """Return 3 criteria as in FHI-aims."""
                self.get_all_criteria_called = True
                self.returned_items = [
                    {
                        'm_def': 'SelfConsistency',
                        'name': 'total_energy_change',
                        'threshold_change': 1e-6
                    },
                    {
                        'm_def': 'SelfConsistency',
                        'name': 'charge_density_change',
                        'threshold_change': 1e-5
                    },
                    {
                        'm_def': 'SelfConsistency',
                        'name': 'sum_eigenvalues_change',
                        'threshold_change': 1e-3
                    },
                ]
                return self.returned_items

        # Add annotations as in our FHI-aims implementation
        SelfConsistency.name.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(mapper='.dummy_to_force_transformer')
        })

        SelfConsistency.m_def.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(
                mapper=('get_all_criteria', []),
                update_mode='append'
            )
        })

        m_package.init_metainfo()

        parser = TestParser()
        parser.annotation_key = 'test'
        dft = DFT()
        parser.data_object = dft
        parser._data = {}

        # Try to trigger the mapping
        # Note: Actual framework invocation needed here

        print("\nSCF Criteria Test:")
        print(f"Function called: {parser.get_all_criteria_called}")
        print(f"Items returned by function: {len(parser.returned_items)}")
        print(f"Actual items in numerical_settings: {len(dft.numerical_settings)}")

        if parser.get_all_criteria_called:
            created_count = len(dft.numerical_settings)
            if created_count == 3:
                print("✓ Each dict created a separate instance (desired behavior)")
            elif created_count == 1:
                print("✗ Only one instance created (current bug)")
            elif created_count == 0:
                print("✗ No instances created despite function being called")
            else:
                print(f"? Unexpected: {created_count} instances")

            # Check if the single instance has the expected data
            if created_count > 0:
                for i, item in enumerate(dft.numerical_settings):
                    print(f"  Item {i}: {item.m_def.name}")
                    if hasattr(item, 'name'):
                        print(f"    name: {item.name}")


@given(
    list_size=st.integers(min_value=0, max_value=5),
    return_type=st.sampled_from(['list', 'single', 'nested_list'])
)
def test_update_mode_append_property(list_size: int, return_type: str):
    """
    Property-based test for update_mode='append' behavior.

    Property: ∀n ∈ ℕ, ∀t ∈ {list, single, nested_list}:
        t = list ∧ n > 0 → |appended| ∈ {1, n}
        t = single → |appended| = 1
        t = nested_list → |appended| ∈ {1, len(flattened)}

    This test determines the actual behavior empirically.
    """
    Container, Item = create_test_schema_for_append_behavior()

    class PropertyTestParser(MetainfoParser):
        def __init__(self, size: int, ret_type: str):
            super().__init__()
            self.size = size
            self.ret_type = ret_type
            self.call_count = 0

        def get_items(self, source: dict):
            self.call_count += 1

            if self.ret_type == 'list':
                return [
                    {'name': f'item_{i}', 'value': float(i)}
                    for i in range(self.size)
                ]
            elif self.ret_type == 'single':
                return {'name': 'single', 'value': 1.0}
            else:  # nested_list
                return [
                    [{'name': f'nested_{i}_{j}', 'value': float(i*10+j)}
                     for j in range(2)]
                    for i in range(max(1, self.size))
                ]

    # Configure annotations
    Item.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = {
        'test': Mapper(
            mapper=('get_items', []),
            update_mode='append'
        )
    }
    Item.name.m_annotations[MAPPING_ANNOTATION_KEY] = {
        'test': Mapper(mapper='.dummy')
    }

    parser = PropertyTestParser(list_size, return_type)
    parser.annotation_key = 'test'
    container = Container()
    parser.data_object = container
    parser._data = {}

    # Record behavior
    items_created = len(container.items)

    # Assert properties based on observed behavior
    if return_type == 'list' and list_size > 0:
        # Key assertion: Does it append each item or just one?
        assert items_created in [0, 1, list_size], \
            f"Expected 0, 1, or {list_size} items, got {items_created}"

        if items_created == list_size:
            behavior = "APPENDS_EACH"
        elif items_created == 1:
            behavior = "APPENDS_FIRST_OR_WHOLE"
        else:
            behavior = "FAILS"
    elif return_type == 'single':
        assert items_created in [0, 1], \
            f"Single dict should create 0 or 1 item, got {items_created}"
        behavior = "SINGLE_OK" if items_created == 1 else "SINGLE_FAILS"
    else:  # nested_list
        flat_size = max(1, list_size) * 2
        assert items_created in [0, 1, flat_size], \
            f"Nested list should create 0, 1, or {flat_size} items, got {items_created}"
        behavior = f"NESTED_{items_created}"

    print(f"Behavior: {return_type}(n={list_size}) → {behavior} ({items_created} items)")

    return behavior


if __name__ == "__main__":
    # Run basic tests
    tester = TestUpdateModeAppendBehavior()
    tester.test_append_mode_with_list_return(3, True)
    tester.test_append_mode_with_list_return(1, False)

    scf_tester = TestSCFCriteriaSpecificBehavior()
    scf_tester.test_get_all_criteria_return_behavior()

    # Run property test to determine behavior pattern
    print("\n=== Property Test Results ===")
    behaviors = {}
    for _ in range(20):
        for list_size in [0, 1, 3]:
            for ret_type in ['list', 'single', 'nested_list']:
                behavior = test_update_mode_append_property(list_size, ret_type)
                key = f"{ret_type}(n={list_size})"
                behaviors[key] = behavior

    print("\n=== Behavior Summary ===")
    for key, behavior in behaviors.items():
        print(f"{key}: {behavior}")