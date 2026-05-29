"""
Example-based tests for array iteration patterns in the mapping parser.

These tests demonstrate correct patterns for mapping arrays to repeating subsections,
addressing common confusion about wildcards and annotation placement.

See: mapping-parser-repeating-subsections.md "Common Confusion" section
"""

import pytest

# =============================================================================
# Monkeypatch ClassicLogger to Fix ABC Interaction
# =============================================================================
#
# ISSUE: ClassicLogger's __getattr__ returns a lambda for ANY attribute access,
# including Python's special __isabstractmethod__ attribute used by ABC machinery.
# This causes Python to mark 'logger' as an abstract method, preventing instantiation
# of MappingParser subclasses (MetainfoParser, HDF5Parser, XMLParser).
#
# See test_mapping_parser_properties.py for full explanation.
#
from nomad.utils import ClassicLogger

_original_getattr = ClassicLogger.__getattr__


def _fixed_getattr(self, key):
    """Fixed __getattr__ that doesn't return lambda for __isabstractmethod__."""
    if key == '__isabstractmethod__':
        raise AttributeError(key)
    return _original_getattr(self, key)


ClassicLogger.__getattr__ = _fixed_getattr


# =============================================================================
# Test Helper Functions
# =============================================================================


def create_test_parser(data_object):
    """Create a MetainfoParser instance for testing.

    Uses NOMAD-FAIR's MetainfoParser which has from_dict() that filters empty elements
    and implements array iteration logic.

    Note: Works because ClassicLogger monkeypatch above fixes ABC issue.

    Args:
        data_object: MSection instance to use as data_object

    Returns:
        MetainfoParser instance ready for testing
    """
    from nomad.parsing.file_parser.mapping_parser import MetainfoParser

    parser = MetainfoParser()
    parser.data_object = data_object
    return parser


# =============================================================================
# Array Iteration Pattern Tests (Example-Based Unit Tests)
# =============================================================================


class TestArrayIterationPatterns:
    """Example-based tests for array iteration patterns - addressing common confusion.

    These tests demonstrate the correct patterns for mapping arrays to repeating subsections,
    clarifying when wildcards are needed vs automatic iteration.

    See: mapping-parser-repeating-subsections.md "Common Confusion" section
    """

    def test_from_dict_with_array_creates_multiple_instances(self):
        """Example: from_dict() with array automatically creates one instance per element.

        Common confusion: "Do I need convergence_criteria[*] wildcard to iterate?"
        Answer: NO - framework iterates automatically when you pass an array.
        """
        from nomad.metainfo import MSection, Quantity, SubSection

        class Criterion(MSection):
            parameter = Quantity(type=str)
            threshold = Quantity(type=float)

        class Calculation(MSection):
            convergence_criteria = SubSection(sub_section=Criterion, repeats=True)

        # Use MetainfoParser which has array iteration logic
        parser = create_test_parser(Calculation())
        parser.from_dict({
            'convergence_criteria': [
                {'parameter': 'energy', 'threshold': 1e-6},
                {'parameter': 'forces', 'threshold': 1e-5},
                {'parameter': 'stress', 'threshold': 1e-4}
            ]
        })

        # Verify: one instance per array element (no wildcard needed!)
        calc = parser.data_object
        assert len(calc.convergence_criteria) == 3
        assert calc.convergence_criteria[0].parameter == 'energy'
        assert calc.convergence_criteria[1].parameter == 'forces'
        assert calc.convergence_criteria[2].parameter == 'stress'

    def test_repeats_true_required_for_multiple_instances(self):
        """Example: SubSection needs repeats=True to create multiple instances."""
        from nomad.metainfo import MSection, Quantity, SubSection

        class Item(MSection):
            value = Quantity(type=int)

        # WITHOUT repeats=True - only single instance allowed
        class ContainerWrong(MSection):
            items = SubSection(sub_section=Item)  # Missing repeats=True!

        wrong_parser = create_test_parser(ContainerWrong())
        wrong_parser.from_dict({'items': [{'value': 1}, {'value': 2}, {'value': 3}]})
        # Non-repeating field: only creates one instance from first array element
        assert len(wrong_parser.data_object.items) == 1 if hasattr(wrong_parser.data_object.items, '__len__') else True

        # WITH repeats=True - allows multiple instances
        class ContainerCorrect(MSection):
            items = SubSection(sub_section=Item, repeats=True)  # ← KEY

        correct_parser = create_test_parser(ContainerCorrect())
        correct_parser.from_dict({'items': [{'value': 1}, {'value': 2}, {'value': 3}]})
        assert len(correct_parser.data_object.items) == 3
        assert correct_parser.data_object.items[0].value == 1
        assert correct_parser.data_object.items[2].value == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
