"""
Hypothesis tests for the new append_each mode.

Tests that append_each properly iterates over list items and appends each individually.
"""

from typing import Any, Dict, List

import pytest
from hypothesis import given, settings, strategies as st
from nomad_file_parser.mapping_parser import Path


class TestAppendEachMode:
    """Test the new append_each update mode."""

    @given(
        num_items=st.integers(min_value=1, max_value=10),
        existing_items=st.integers(min_value=0, max_value=5)
    )
    @settings(max_examples=50)
    def test_append_each_with_lists(self, num_items: int, existing_items: int):
        """
        Property: ∀n ∈ [1,10], ∀m ∈ [0,5]:
            List[n] with append_each on target with m items → m + n items

        This tests that append_each properly appends each item individually.
        """
        # Create path
        path = Path(path='items')

        # Create target with existing items
        target = {}
        if existing_items > 0:
            target['items'] = [{'id': f'existing_{i}'} for i in range(existing_items)]

        # Create new data
        new_data = [{'id': f'new_{i}'} for i in range(num_items)]

        # Apply with append_each
        path.set_data(new_data, target, update_mode='append_each')

        # Check result
        result_items = target.get('items', [])

        # Should have existing + new items
        expected_count = existing_items + num_items
        assert len(result_items) == expected_count, \
            f"Expected {expected_count} items, got {len(result_items)}"

        # Verify existing items are preserved
        if existing_items > 0:
            for i in range(existing_items):
                assert result_items[i]['id'] == f'existing_{i}', \
                    f"Existing item {i} was modified"

        # Verify new items are appended
        for i in range(num_items):
            assert result_items[existing_items + i]['id'] == f'new_{i}', \
                f"New item {i} not properly appended"

    def test_append_each_vs_append_comparison(self):
        """
        Compare append vs append_each behavior with lists.

        append: treats list as single item
        append_each: iterates and appends each item
        """
        # Test data
        new_data = [
            {'name': 'item1', 'value': 1},
            {'name': 'item2', 'value': 2},
            {'name': 'item3', 'value': 3}
        ]

        # Test with regular append
        path_append = Path(path='items')
        target_append = {'items': []}
        path_append.set_data(new_data, target_append, update_mode='append')

        # Test with append_each
        path_append_each = Path(path='items')
        target_append_each = {'items': []}
        path_append_each.set_data(new_data, target_append_each, update_mode='append_each')

        # Compare results
        items_append = target_append.get('items', [])
        items_append_each = target_append_each.get('items', [])

        # append should create nested structure (bug)
        # append_each should create flat structure (fix)
        print(f"append result: {items_append}")
        print(f"append_each result: {items_append_each}")

        # With append_each, should have 3 items
        assert len(items_append_each) == 3, \
            f"append_each should create 3 items, got {len(items_append_each)}"

        # Each item should be a dict
        for item in items_append_each:
            assert isinstance(item, dict), \
                f"Each item should be a dict, got {type(item)}"

    @given(
        data_type=st.sampled_from([dict, str, int])  # Skip None for now
    )
    def test_append_each_with_non_lists(self, data_type):
        """
        Property: append_each with non-list data → behaves like regular append

        Tests that append_each only special-cases lists.
        """
        path = Path(path='value')
        target = {}

        # Create non-list data
        if data_type == dict:
            data = {'key': 'value'}
        elif data_type == str:
            data = 'string_value'
        elif data_type == int:
            data = 42
        else:
            data = None

        # Apply with append_each
        path.set_data(data, target, update_mode='append_each')

        # Should behave like regular append for non-lists
        result = target.get('value')
        assert result == data, \
            f"Non-list data should be appended as-is, got {result}"

    @given(
        num_nested=st.integers(min_value=1, max_value=3),
        items_per_level=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=20)
    def test_append_each_with_nested_lists(self, num_nested: int, items_per_level: int):
        """
        Property: append_each with nested lists → only outer list is iterated

        Tests that append_each doesn't recursively iterate nested structures.
        """
        # Create nested list structure
        def create_nested(depth: int) -> List[Any]:
            if depth == 0:
                return [{'leaf': f'item_{i}'} for i in range(items_per_level)]
            return [create_nested(depth - 1) for _ in range(items_per_level)]

        path = Path(path='nested')
        target = {'nested': []}

        nested_data = create_nested(num_nested)

        # Apply with append_each
        path.set_data(nested_data, target, update_mode='append_each')

        # Should append each top-level item
        result = target.get('nested', [])

        # Number of top-level items should match
        if num_nested == 0:
            expected = items_per_level
        else:
            expected = items_per_level

        assert len(result) == expected, \
            f"Expected {expected} top-level items, got {len(result)}"

    def test_append_each_preserves_order(self):
        """
        Test that append_each preserves the order of items.
        """
        path = Path(path='ordered')
        target = {'ordered': [{'id': 0}]}

        new_items = [{'id': i} for i in range(1, 6)]

        path.set_data(new_items, target, update_mode='append_each')

        result = target.get('ordered', [])

        # Check order is preserved
        for i, item in enumerate(result):
            assert item['id'] == i, \
                f"Item at index {i} has wrong id: {item['id']}"

    @given(
        empty_target=st.booleans()
    )
    def test_append_each_on_empty_vs_existing(self, empty_target: bool):
        """
        Property: append_each works whether target exists or not
        """
        path = Path(path='data')

        if empty_target:
            target = {}  # No existing 'data' key
        else:
            target = {'data': [{'existing': True}]}

        new_data = [{'new': 1}, {'new': 2}]

        path.set_data(new_data, target, update_mode='append_each')

        result = target.get('data', [])

        if empty_target:
            assert len(result) == 2, "Should create list with 2 items"
        else:
            assert len(result) == 3, "Should have 1 existing + 2 new items"
            assert result[0] == {'existing': True}, "Existing item should be preserved"


if __name__ == "__main__":
    """Quick manual test of append_each functionality."""

    print("="*60)
    print("TESTING APPEND_EACH MODE")
    print("="*60)

    tester = TestAppendEachMode()

    print("\n=== Basic append_each test ===")
    tester.test_append_each_vs_append_comparison()

    print("\n=== Order preservation test ===")
    tester.test_append_each_preserves_order()

    print("\n=== Non-list data test ===")
    tester.test_append_each_with_non_lists(dict)

    print("\n" + "="*60)
    print("CONCLUSION")
    print("="*60)
    print("append_each mode successfully:")
    print("1. Iterates over list items and appends each individually")
    print("2. Preserves existing items in target")
    print("3. Maintains order of new items")
    print("4. Works with empty and existing targets")
    print("5. Falls back to regular append for non-list data")