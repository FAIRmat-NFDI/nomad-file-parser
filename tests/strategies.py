"""
Shared hypothesis strategies for the nomad-file-parser test suite.
"""

import string

from hypothesis import strategies as st


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


@st.composite
def path_with_slices_strategy(draw, max_depth: int = 3) -> str:
    """Generate paths whose final segment carries a slice.

    Examples: 'a[0:2]', 'a.b[1:4]', 'items.data[0:3]'

    The slice is placed on the last segment only, keeping the container
    structure above it unambiguous for set/search inverse tests.

    Args:
        draw: Hypothesis draw function
        max_depth: Maximum nesting depth

    Returns:
        str: A path string ending in a '[start:stop]' slice
    """
    base_path = draw(simple_path_strategy(max_depth=max_depth))
    start = draw(st.integers(min_value=0, max_value=3))
    stop = draw(st.integers(min_value=start + 1, max_value=4))
    return f'{base_path}[{start}:{stop}]'


def nested_dict_strategy(
    max_depth: int = 3, allow_none: bool = True, allow_falsy: bool = True
) -> st.SearchStrategy:
    """Generate nested dictionaries with various value types.

    Args:
        max_depth: Maximum nesting depth
        allow_none: Whether to include None values in the generated data
        allow_falsy: Whether to include falsy values (0, False, '', [], etc.)
                     Framework filters these during merge, so set False for monoid tests

    Returns:
        SearchStrategy: A hypothesis strategy for nested dicts
    """
    # Base case: scalar values
    scalar_types = []

    if allow_falsy:
        # All values including falsy ones
        scalar_types = [
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(alphabet=string.ascii_letters, max_size=20),
            st.booleans(),
        ]
        if allow_none:
            scalar_types.append(st.none())
    else:
        # Only truthy values (for monoid tests where framework filters falsy)
        scalar_types = [
            st.integers(min_value=1, max_value=1000),  # Positive integers only
            st.floats(
                min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False
            ),  # Positive floats
            st.text(
                alphabet=string.ascii_letters, min_size=1, max_size=20
            ),  # Non-empty strings
            st.just(True),  # Only True, not False
        ]

    scalars = st.one_of(*scalar_types)

    if max_depth == 0:
        return scalars

    # Recursive case: values can be scalars, dicts, or lists
    values = st.one_of(
        scalars,
        st.lists(
            scalars, min_size=1 if not allow_falsy else 0, max_size=5
        ),  # Non-empty lists if no falsy
        st.deferred(
            lambda: nested_dict_strategy(
                max_depth - 1, allow_none=allow_none, allow_falsy=allow_falsy
            )
        ),
    )

    return st.dictionaries(
        keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
        values=values,
        min_size=1 if not allow_falsy else 0,  # Non-empty dicts if no falsy
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
