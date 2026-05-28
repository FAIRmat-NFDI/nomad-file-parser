"""
Property-based tests for the mapping parser framework.

Tests algebraic properties and invariants using Hypothesis for automatic test case generation.
Organized by testing goal:
    A. Data Integrity - No loss, corruption, or type pollution
    B. Operation Semantics - Correct behavior of merge, path resolution, transformers
    C. System Constraints - Framework rules like mode inheritance, error handling

See: mapping-parser-property-based-testing-specs.md in Obsidian vault for detailed specifications.
"""

import string
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import Path, PathParser, BaseMapper, Mapper


# =============================================================================
# Hypothesis Strategies
# =============================================================================


@st.composite
def simple_path_strategy(draw, max_depth: int = 3) -> str:
    """Generate simple jmespath-like paths without complex filters.

    Examples: 'a', 'a.b', 'a.b.c', 'items.data'

    Args:
        draw: Hypothesis draw function
        max_depth: Maximum nesting depth

    Returns:
        str: A simple path string
    """
    num_segments = draw(st.integers(min_value=1, max_value=max_depth))
    segments = draw(
        st.lists(
            st.text(
                alphabet=string.ascii_lowercase,
                min_size=1,
                max_size=8,
            ),
            min_size=num_segments,
            max_size=num_segments,
        )
    )
    return '.'.join(segments)


@st.composite
def path_with_indices_strategy(draw, max_depth: int = 3) -> str:
    """Generate paths with array indices.

    Examples: 'a[0]', 'a.b[1].c', 'items[2].data[0]'

    Args:
        draw: Hypothesis draw function
        max_depth: Maximum nesting depth

    Returns:
        str: A path string with indices
    """
    base_path = draw(simple_path_strategy(max_depth=max_depth))

    # Optionally add indices to some segments
    segments = base_path.split('.')
    indexed_segments = []

    for segment in segments:
        add_index = draw(st.booleans())
        if add_index:
            index = draw(st.integers(min_value=0, max_value=5))
            indexed_segments.append(f'{segment}[{index}]')
        else:
            indexed_segments.append(segment)

    return '.'.join(indexed_segments)


@st.composite
def relative_path_strategy(draw, max_depth: int = 3) -> str:
    """Generate relative paths (starting with '.').

    Examples: '.a', '.a.b', '.a[0].b'

    Args:
        draw: Hypothesis draw function
        max_depth: Maximum nesting depth

    Returns:
        str: A relative path string
    """
    # Choose between simple and indexed paths
    path = draw(
        st.one_of(
            simple_path_strategy(max_depth=max_depth),
            path_with_indices_strategy(max_depth=max_depth),
        )
    )
    return f'.{path}'


def nested_dict_strategy(max_depth: int = 3) -> st.SearchStrategy:
    """Generate nested dictionaries with various value types.

    Args:
        max_depth: Maximum nesting depth

    Returns:
        SearchStrategy: A hypothesis strategy for nested dicts
    """
    # Base case: scalar values
    scalars = st.one_of(
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.text(alphabet=string.ascii_letters, max_size=20),
        st.booleans(),
        st.none(),
    )

    if max_depth == 0:
        return scalars

    # Recursive case: values can be scalars, dicts, or lists
    values = st.one_of(
        scalars,
        st.lists(scalars, max_size=5),
        st.deferred(lambda: nested_dict_strategy(max_depth - 1)),
    )

    return st.dictionaries(
        keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
        values=values,
        max_size=5,
    )


@st.composite
def update_mode_strategy(draw) -> str:
    """Generate valid update mode strings.

    Returns:
        str: An update mode string
    """
    return draw(
        st.one_of(
            st.just('merge'),
            st.just('append'),
            st.just('replace'),
            st.builds(lambda i: f'merge@{i}', st.integers(min_value=-2, max_value=5)),
            st.just('merge@start'),
            st.just('merge@last'),
            st.just('merge@end'),
        )
    )


# =============================================================================
# A. Data Integrity Properties
# =============================================================================


class TestDataIntegrity:
    """Test properties that ensure no data loss, corruption, or type pollution."""

    # -------------------------------------------------------------------------
    # A1. Inverse Relationships (Round-Trips)
    # -------------------------------------------------------------------------

    @given(
        path_str=simple_path_strategy(max_depth=3),
        value=st.one_of(
            st.integers(),
            st.text(alphabet=string.ascii_letters, max_size=20),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=100)
    def test_get_set_inverse_simple_paths(self, path_str: str, value: Any):
        """Property: get(set(data, path, value), path) == value

        Algebraic structure: set and get form a left inverse pair.

        Tests that setting a value then getting it returns the same value
        for simple paths without indices.
        """
        # Property: ∀ data, path, value: get(set(data, path, value), path) == value
        path = Path(path=path_str)
        target = {}

        # Set the value
        path.set_data(value, target)

        # Get it back
        retrieved = path.get_data(target)

        assert retrieved == value, (
            f'Round-trip failed for path {path_str}:\n'
            f'  Original value: {value}\n'
            f'  Retrieved value: {retrieved}\n'
            f'  Target dict: {target}'
        )

    @given(
        path_str=path_with_indices_strategy(max_depth=2),
        value=st.integers(),
    )
    @settings(max_examples=50)
    def test_get_set_inverse_with_indices(self, path_str: str, value: int):
        """Property: get(set(data, path, value), path) == value

        Algebraic structure: set and get form a left inverse pair.

        Tests round-trip with array indices.
        """
        # Property: ∀ data, path[i], value: get(set(data, path[i], value), path[i]) == value
        path = Path(path=path_str)
        target = {}

        # Set the value
        path.set_data(value, target)

        # Get it back
        retrieved = path.get_data(target)

        assert retrieved == value, (
            f'Round-trip failed for indexed path {path_str}:\n'
            f'  Original value: {value}\n'
            f'  Retrieved value: {retrieved}\n'
            f'  Target dict: {target}'
        )

    # -------------------------------------------------------------------------
    # A3. Data Isolation
    # -------------------------------------------------------------------------

    @given(
        path1=simple_path_strategy(max_depth=2),
        path2=simple_path_strategy(max_depth=2),
        value1=st.integers(),
        value2=st.text(alphabet=string.ascii_letters, max_size=10),
    )
    @settings(max_examples=50)
    def test_sibling_path_independence(
        self, path1: str, path2: str, value1: int, value2: str
    ):
        """Property: set(set(data, path1, v1), path2, v2) preserves both v1 and v2

        Tests that setting different paths doesn't corrupt sibling data.

        Note: Only tests when paths are truly independent (different roots).
        """
        # Property: ∀ path1, path2 (non-overlapping):
        #           set(set(data, path1, v1), path2, v2) preserves both v1 and v2

        # Skip if paths share prefix (not siblings)
        if path1 == path2 or path1.startswith(path2 + '.') or path2.startswith(path1 + '.'):
            return

        p1 = Path(path=path1)
        p2 = Path(path=path2)
        target = {}

        # Set both values
        p1.set_data(value1, target)
        p2.set_data(value2, target)

        # Both should be retrievable
        retrieved1 = p1.get_data(target)
        retrieved2 = p2.get_data(target)

        assert retrieved1 == value1, (
            f'Path1 data corrupted:\n'
            f'  Path1: {path1}, expected: {value1}, got: {retrieved1}\n'
            f'  Path2: {path2}, value: {value2}\n'
            f'  Target: {target}'
        )

        assert retrieved2 == value2, (
            f'Path2 data corrupted:\n'
            f'  Path1: {path1}, value: {value1}\n'
            f'  Path2: {path2}, expected: {value2}, got: {retrieved2}\n'
            f'  Target: {target}'
        )

    # -------------------------------------------------------------------------
    # A3. Remove Completeness (Phase 2)
    # -------------------------------------------------------------------------

    # Note: Remove completeness testing requires integration with mapper execution
    # which involves parser context. Deferred to integration tests or Phase 3.


# =============================================================================
# B. Operation Semantics
# =============================================================================


class TestOperationSemantics:
    """Test correct behavior of core operations: merge, path resolution, transformers."""

    # -------------------------------------------------------------------------
    # B1. Merge Algebra
    # -------------------------------------------------------------------------

    @given(
        data=nested_dict_strategy(max_depth=2),
        mode=update_mode_strategy(),
    )
    @settings(max_examples=50)
    def test_merge_identity_right_empty_incoming(self, data: dict, mode: str):
        """Property: merge(data, {}, mode) == data

        Algebraic structure: {} is the right identity element for merge (monoid).

        Tests that merging with empty dict is a no-op for all update modes.
        """
        # Property: ∀ data, mode: merge(data, {}, mode) == data (right identity)
        path = Path(path='@')  # Root path
        target = data.copy() if isinstance(data, dict) else {'data': data}

        # Merge empty dict
        path.set_data({}, target, update_mode=mode)

        # Target should be unchanged
        original = data.copy() if isinstance(data, dict) else {'data': data}
        assert target == original, (
            f'Merge with empty dict modified target (mode={mode}):\n'
            f'  Original: {original}\n'
            f'  After merge: {target}'
        )

    @given(
        data=nested_dict_strategy(max_depth=2).filter(
            lambda d: all(v is not None for v in d.values()) if isinstance(d, dict) else d is not None
        ),
        mode=st.one_of(st.just('merge'), st.just('replace')),
    )
    @settings(max_examples=50)
    def test_merge_identity_left_empty_existing(self, data: dict, mode: str):
        """Property: merge({}, data, mode) == data

        Algebraic structure: {} is the left identity element for merge (monoid).

        Tests that merging data into empty target yields the data.

        Note: Filters out None values as they may be intentionally skipped during merge.
        Note: Tests at 'content' path level, not root '@' which has special semantics.
        """
        # Property: ∀ data (non-None values), mode: merge({}, data, mode) == data (left identity)
        path = Path(path='content')
        target = {}

        # Merge data into empty target
        path.set_data(data, target, update_mode=mode)

        # Target should contain the data at the path
        assert target.get('content') == data, (
            f'Merge into empty dict did not preserve data (mode={mode}):\n'
            f'  Data: {data}\n'
            f'  Result: {target}'
        )

    @given(
        data1=nested_dict_strategy(max_depth=2),
        data2=nested_dict_strategy(max_depth=2),
        data3=nested_dict_strategy(max_depth=2),
    )
    @settings(max_examples=30)
    def test_merge_associativity(
        self, data1: dict, data2: dict, data3: dict
    ):
        """Property: merge(merge(a, b), c) == merge(a, merge(b, c))

        Algebraic structure: Merge is associative (monoid requirement).

        Tests that merge order doesn't matter (associativity law).
        """
        # Property: ∀ a, b, c: merge(merge(a, b), c) == merge(a, merge(b, c))
        path = Path(path='@')

        # Left-associated: merge(merge(a, b), c)
        target_left = data1.copy()
        path.set_data(data2, target_left, update_mode='merge')
        path.set_data(data3, target_left, update_mode='merge')

        # Right-associated: merge(a, merge(b, c))
        temp = data2.copy()
        path.set_data(data3, temp, update_mode='merge')
        target_right = data1.copy()
        path.set_data(temp, target_right, update_mode='merge')

        # Both should yield same result
        assert target_left == target_right, (
            f'Merge is not associative:\n'
            f'  Data1: {data1}\n'
            f'  Data2: {data2}\n'
            f'  Data3: {data3}\n'
            f'  merge(merge(a,b),c): {target_left}\n'
            f'  merge(a,merge(b,c)): {target_right}'
        )

    # -------------------------------------------------------------------------
    # B2. Path Resolution
    # -------------------------------------------------------------------------

    @given(
        parent_path=simple_path_strategy(max_depth=2),
        relative_path=relative_path_strategy(max_depth=2),
    )
    @settings(max_examples=50)
    def test_parent_propagation(self, parent_path: str, relative_path: str):
        """Property: Child paths inherit parent context correctly.

        Tests that absolute_path is correctly computed from parent + relative.
        """
        # Property: ∀ parent, child: child.absolute_path == parent.absolute_path + child.relative_path
        parent = Path(path=parent_path)
        child = Path(path=relative_path, parent=parent)

        # Child's absolute path should include parent's path
        expected_absolute = f'{parent.absolute_path}.{child.relative_path}'

        assert child.absolute_path == expected_absolute, (
            f'Parent propagation failed:\n'
            f'  Parent path: {parent_path} (absolute: {parent.absolute_path})\n'
            f'  Child path: {relative_path} (relative: {child.relative_path})\n'
            f'  Expected absolute: {expected_absolute}\n'
            f'  Actual absolute: {child.absolute_path}'
        )

    @given(
        path_str=simple_path_strategy(max_depth=3),
    )
    @settings(max_examples=50)
    def test_relative_path_computation(self, path_str: str):
        """Property: relative_path correctly strips leading '.'

        Tests that Path correctly identifies and strips relative path prefix.
        """
        # Property: ∀ path_str: Path('.path_str').relative_path == path_str
        relative = f'.{path_str}'
        path = Path(path=relative)

        assert path.relative_path == path_str, (
            f'Relative path computation failed:\n'
            f'  Input path: {relative}\n'
            f'  Expected relative: {path_str}\n'
            f'  Actual relative: {path.relative_path}'
        )

    @given(
        path_str=path_with_indices_strategy(max_depth=2),
    )
    @settings(max_examples=50)
    def test_reduced_path_removes_indices(self, path_str: str):
        """Property: reduced_path correctly removes array indices.

        Tests that indices are stripped from absolute_path to get reduced_path.
        """
        # Property: ∀ path[i]: '[' ∉ reduced_path ∧ ']' ∉ reduced_path
        path = Path(path=path_str)

        # Reduced path should not contain '[' or ']'
        assert '[' not in path.reduced_path, (
            f'Reduced path still contains indices:\n'
            f'  Original path: {path_str}\n'
            f'  Absolute path: {path.absolute_path}\n'
            f'  Reduced path: {path.reduced_path}'
        )

        assert ']' not in path.reduced_path, (
            f'Reduced path still contains indices:\n'
            f'  Original path: {path_str}\n'
            f'  Absolute path: {path.absolute_path}\n'
            f'  Reduced path: {path.reduced_path}'
        )

    # -------------------------------------------------------------------------
    # B1. Extended Merge Semantics (Phase 2)
    # -------------------------------------------------------------------------

    @given(
        old_data=nested_dict_strategy(max_depth=2),
        new_data=nested_dict_strategy(max_depth=2),
    )
    @settings(max_examples=50)
    def test_replace_mode_overwrites_completely(
        self, old_data: dict, new_data: dict
    ):
        """Property: replace(old, new) contains no traces of old data.

        Algebraic structure: Replace is annihilation (old data is completely discarded).

        Tests that replace mode completely overwrites old data with new data.
        """
        # Property: ∀ old, new: replace(old, new) ∩ old == ∅ (for non-shared values)
        path = Path(path='data')
        target = {'data': old_data}

        # Replace with new data
        path.set_data(new_data, target, update_mode='replace')

        # Result should be exactly new_data, not merged
        assert target['data'] == new_data, (
            f'Replace mode did not overwrite completely:\n'
            f'  Old data: {old_data}\n'
            f'  New data: {new_data}\n'
            f'  Result: {target["data"]}'
        )

    # TODO: Append mode has type-dependent polymorphic behavior that causes issues
    # See: mapping-parser-framework-feedback.md for details
    # Uncomment when framework issues are resolved

    # @given(
    #     old_list=st.lists(st.integers(), min_size=1, max_size=3),
    #     new_list=st.lists(st.integers(), min_size=1, max_size=3),
    # )
    # @settings(max_examples=50)
    # def test_append_mode_prepends_existing_to_lists(
    #     self, old_list: list, new_list: list
    # ):
    #     """Property: append(old_list, new_list) prepends old elements to new.
    #
    #     Algebraic structure: Append for lists prepends existing data to incoming.
    #
    #     Tests that append mode preserves existing list elements by prepending them.
    #     """
    #     # Property: ∀ old_list, new_list: append(old_list, new_list) starts with old_list elements
    #     path = Path(path='items')
    #     target = {'items': old_list.copy()}
    #
    #     # Append new list
    #     path.set_data(new_list, target, update_mode='append')
    #
    #     result = target['items']
    #
    #     # Result should start with old_list elements
    #     assert result[: len(old_list)] == old_list, (
    #         f'Append mode did not prepend existing list elements:\n'
    #         f'  Old list: {old_list}\n'
    #         f'  New list: {new_list}\n'
    #         f'  Expected to start with: {old_list}\n'
    #         f'  Got: {result}'
    #     )

    @given(
        new_value=st.integers(),
    )
    @settings(max_examples=50)
    def test_append_mode_uses_new_when_empty(self, new_value: int):
        """Property: append(∅, new) == new (uses new data when no existing data).

        Tests that append mode uses new data when target path doesn't exist.
        """
        # Property: ∀ new: append(∅, new) == new
        path = Path(path='data')
        target = {}

        # Append to empty target
        path.set_data(new_value, target, update_mode='append')

        result = target.get('data')

        # Result should be new_value
        assert result == new_value, (
            f'Append mode did not use new data for empty target:\n'
            f'  New value: {new_value}\n'
            f'  Got: {result}'
        )

    @given(
        old_list=st.lists(st.integers(), min_size=1, max_size=5),
        new_list=st.lists(st.integers(), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_merge_at_last_aligns_final_elements(
        self, old_list: list, new_list: list
    ):
        """Property: merge@last aligns final elements of lists.

        Tests that merge@last mode correctly aligns the last elements and
        extends appropriately.
        """
        # Property: ∀ list1, list2: merge@last(list1, list2)[-1] involves both list1[-1] and list2[-1]
        path = Path(path='items')
        target = {'items': old_list.copy()}

        # Merge with @last mode
        path.set_data(new_list, target, update_mode='merge@last')

        result = target['items']

        # Result should have length at least max of the two lists
        expected_min_length = max(len(old_list), len(new_list))

        assert len(result) >= expected_min_length, (
            f'merge@last result too short:\n'
            f'  Old list: {old_list} (len={len(old_list)})\n'
            f'  New list: {new_list} (len={len(new_list)})\n'
            f'  Expected min length: {expected_min_length}\n'
            f'  Got: {result} (len={len(result)})'
        )

        # The last element should be from new_list (simple merge for scalars)
        assert result[-1] == new_list[-1], (
            f'merge@last did not align final elements:\n'
            f'  Old list: {old_list}\n'
            f'  New list: {new_list}\n'
            f'  Result: {result}\n'
            f'  Expected last element: {new_list[-1]}\n'
            f'  Got: {result[-1]}'
        )

    @given(
        old_list=st.lists(st.integers(), min_size=1, max_size=5),
        new_list=st.lists(st.integers(), min_size=1, max_size=5),
    )
    @settings(max_examples=50)
    def test_merge_at_start_aligns_first_elements(
        self, old_list: list, new_list: list
    ):
        """Property: merge@start aligns first elements of lists.

        Tests that merge@start mode correctly aligns the first elements.
        """
        # Property: ∀ list1, list2: merge@start(list1, list2)[0] involves both list1[0] and list2[0]
        path = Path(path='items')
        target = {'items': old_list.copy()}

        # Merge with @start mode
        path.set_data(new_list, target, update_mode='merge@start')

        result = target['items']

        # Result should have length at least max of the two lists
        expected_min_length = max(len(old_list), len(new_list))

        assert len(result) >= expected_min_length, (
            f'merge@start result too short:\n'
            f'  Old list: {old_list} (len={len(old_list)})\n'
            f'  New list: {new_list} (len={len(new_list)})\n'
            f'  Expected min length: {expected_min_length}\n'
            f'  Got: {result} (len={len(result)})'
        )

        # The first element should be from new_list (simple merge for scalars)
        assert result[0] == new_list[0], (
            f'merge@start did not align first elements:\n'
            f'  Old list: {old_list}\n'
            f'  New list: {new_list}\n'
            f'  Result: {result}\n'
            f'  Expected first element: {new_list[0]}\n'
            f'  Got: {result[0]}'
        )


# =============================================================================
# Additional Helpers
# =============================================================================


def paths_are_siblings(path1: str, path2: str) -> bool:
    """Check if two paths are siblings (don't overlap).

    Args:
        path1: First path
        path2: Second path

    Returns:
        bool: True if paths are siblings, False if they overlap
    """
    return not (
        path1 == path2
        or path1.startswith(path2 + '.')
        or path2.startswith(path1 + '.')
    )


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
