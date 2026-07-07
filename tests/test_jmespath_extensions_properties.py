"""
Property-based tests for the custom jmespath extensions in mapping_parser.

The framework extends jmespath with bidirectional access: `ParsedResult.set()`
creates missing paths and writes data, while `search()` reads. These tests check
the algebraic contract between the two directions:

    A. Set/Search inverse - set(data, v) followed by search(data) recovers v
    B. Slice semantics - broadcast and element-wise mapping over `[start:stop]`
    C. Pop semantics - retrieval with pop=True removes exactly the target
    D. Differential oracle - search agrees with vanilla jmespath on dict-only data
"""

import copy
import string

import jmespath
from hypothesis import given
from hypothesis import strategies as st
from strategies import (
    path_with_indices_strategy,
    path_with_slices_strategy,
    simple_path_strategy,
)

from nomad_file_parser.mapping_parser import JmespathParser, PathParser

scalar_value_strategy = st.one_of(
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(alphabet=string.ascii_letters, min_size=1, max_size=10),
)


@st.composite
def negative_index_path_strategy(draw) -> str:
    """Generate a path ending in a negative index, e.g. 'items[-2]'."""
    key = draw(st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6))
    offset = draw(st.integers(min_value=1, max_value=3))
    return f'{key}[-{offset}]'


def dict_only_strategy(max_depth: int = 3) -> st.SearchStrategy:
    """Nested dicts with scalar leaves and no lists (vanilla-jmespath comparable)."""
    scalars = scalar_value_strategy
    if max_depth == 0:
        return scalars
    return st.dictionaries(
        keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=6),
        values=st.one_of(
            scalars, st.deferred(lambda: dict_only_strategy(max_depth - 1))
        ),
        min_size=1,
        max_size=4,
    )


@st.composite
def dict_only_data_and_path(draw) -> tuple[dict, str]:
    """Draw dict-only data plus a path that walks into it (possibly stopping early)."""
    data = draw(dict_only_strategy())
    segments = []
    node = data
    while isinstance(node, dict) and node:
        key = draw(st.sampled_from(sorted(node)))
        segments.append(key)
        node = node[key]
        if not isinstance(node, dict) or not node or draw(st.booleans()):
            break
    return data, '.'.join(segments)


class TestSetSearchInverse:
    """set(data, v) followed by search(data) must recover v."""

    @given(path=simple_path_strategy(), value=scalar_value_strategy)
    def test_simple_path_inverse(self, path: str, value):
        parsed = JmespathParser().parse(path)
        data: dict = {}
        parsed.set(data, value)
        assert parsed.search(data) == value

    @given(path=path_with_indices_strategy(), value=scalar_value_strategy)
    def test_indexed_path_inverse(self, path: str, value):
        parsed = JmespathParser().parse(path)
        data: dict = {}
        parsed.set(data, value)
        assert parsed.search(data) == value

    @given(path=negative_index_path_strategy(), value=scalar_value_strategy)
    def test_negative_index_inverse(self, path: str, value):
        parsed = JmespathParser().parse(path)
        data: dict = {}
        parsed.set(data, value)
        assert parsed.search(data) == value

    @given(path=simple_path_strategy(), value=scalar_value_strategy)
    def test_search_does_not_create_paths(self, path: str, value):
        """Search mode must not mutate the source, even for missing paths."""
        data = {'unrelated': value}
        snapshot = copy.deepcopy(data)
        JmespathParser().parse(path).search(data)
        assert data == snapshot


class TestSliceOperations:
    """Slice set semantics: broadcast for scalars, element-wise for matching lists."""

    @given(
        path=path_with_slices_strategy(),
        list_length=st.integers(min_value=4, max_value=8),
        fill=st.integers(min_value=-100, max_value=100),
        value=st.integers(min_value=1000, max_value=2000),
    )
    def test_slice_broadcast_scalar(
        self, path: str, list_length: int, fill: int, value: int
    ):
        """Setting a scalar over [start:stop] writes it to every slice position."""
        base, slice_part = path.rsplit('[', maxsplit=1)
        start, stop = (int(i) for i in slice_part.rstrip(']').split(':'))

        # Build data with the target list pre-populated (slices do not create paths)
        data: dict = {}
        JmespathParser().parse(base).set(data, [fill] * list_length)
        parsed = JmespathParser().parse(path)

        parsed.set(data, value)

        result = JmespathParser().parse(base).search(data)
        assert result[start:stop] == [value] * (stop - start)
        # Positions outside the slice are untouched
        assert result[:start] == [fill] * start
        assert result[stop:] == [fill] * (list_length - stop)

    @given(
        path=path_with_slices_strategy(),
        list_length=st.integers(min_value=4, max_value=8),
        fill=st.integers(min_value=-100, max_value=100),
        data_values=st.data(),
    )
    def test_slice_elementwise_mapping(
        self, path: str, list_length: int, fill: int, data_values
    ):
        """Setting a list matching the slice width maps element-wise."""
        base, slice_part = path.rsplit('[', maxsplit=1)
        start, stop = (int(i) for i in slice_part.rstrip(']').split(':'))
        width = stop - start
        values = data_values.draw(
            st.lists(
                st.integers(min_value=1000, max_value=2000),
                min_size=width,
                max_size=width,
            )
        )

        data: dict = {}
        JmespathParser().parse(base).set(data, [fill] * list_length)

        JmespathParser().parse(path).set(data, values)

        result = JmespathParser().parse(base).search(data)
        assert result[start:stop] == values


class TestPopSemantics:
    """pop=True retrieval returns the value and removes exactly the target."""

    @given(path=simple_path_strategy(), value=scalar_value_strategy)
    def test_pop_returns_value_and_removes(self, path: str, value):
        parser = PathParser(parser_name='jmespath')
        data: dict = {}
        parser.set_data(path, data, value)

        popped = parser.get_data(path, data, pop=True)

        assert popped == value
        assert parser.get_data(path, data) is None

    @given(
        path=simple_path_strategy(max_depth=2),
        sibling_key=st.text(alphabet=string.ascii_uppercase, min_size=1, max_size=5),
        value=scalar_value_strategy,
        sibling_value=scalar_value_strategy,
    )
    def test_pop_preserves_siblings(
        self, path: str, sibling_key: str, value, sibling_value
    ):
        """Popping one top-level branch leaves an unrelated branch intact."""
        parser = PathParser(parser_name='jmespath')
        data: dict = {sibling_key: sibling_value}
        parser.set_data(path, data, value)
        snapshot_sibling = copy.deepcopy(data[sibling_key])

        parser.get_data(path, data, pop=True)

        assert data[sibling_key] == snapshot_sibling


class TestDifferentialVanillaJmespath:
    """On dict-only data, the extended search must agree with vanilla jmespath."""

    @given(data_and_path=dict_only_data_and_path())
    def test_search_matches_vanilla(self, data_and_path: tuple[dict, str]):
        data, path = data_and_path
        snapshot = copy.deepcopy(data)

        custom = JmespathParser().parse(path).search(data)
        vanilla = jmespath.search(path, data)

        assert custom == vanilla
        assert data == snapshot

    @given(data=dict_only_strategy(), path=simple_path_strategy())
    def test_search_matches_vanilla_on_arbitrary_path(self, data: dict, path: str):
        """Also for paths not derived from the data (mostly misses)."""
        custom = JmespathParser().parse(path).search(data)
        vanilla = jmespath.search(path, data)
        assert custom == vanilla

    @given(
        first=st.integers(min_value=0, max_value=100),
        last=st.integers(min_value=101, max_value=200),
    )
    def test_list_field_access_deviates_from_vanilla(self, first: int, last: int):
        """Characterization: field access on a list takes the LAST element.

        Vanilla jmespath returns None for field access on a list; the custom
        `TreeInterpreter.visit_field` instead descends into `value[-1]`. This is
        a deliberate framework deviation - pinned here so a change is noticed.
        """
        data = {'a': [{'b': first}, {'b': last}]}
        assert jmespath.search('a.b', data) is None
        assert JmespathParser().parse('a.b').search(data) == last
