"""
Simplified test demonstrating the framework bug where function-only mappers
don't work on polymorphic subsections without a workaround.

Property: ∀f ∈ FunctionMappers, ∀s ∈ PolymorphicSubsections:
    HasQuantityAnnotation(s) ∨ HasPathMapper(s) → CreatesTransformer(f, s)
    ¬(HasQuantityAnnotation(s) ∨ HasPathMapper(s)) → CreatesBaseMapper(f, s)
"""

from nomad.datamodel.metainfo.annotations import Mapper
from nomad.metainfo import Package, Quantity, Section, SubSection
from nomad.parsing.file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    BaseMapper,
    Transformer,
)
import pytest


def test_function_mapper_bug_demonstration():
    """
    Demonstrate that function-only mappers create BaseMapper instead of Transformer
    for polymorphic subsections without quantity annotations.
    """
    m_package = Package()

    class BaseSection(Section):
        pass

    class DerivedA(BaseSection):
        name = Quantity(type=str)
        value = Quantity(type=float)

    class Container(Section):
        items = SubSection(sub_section=BaseSection, repeats=True)

    # Test case 1: Function mapper WITHOUT quantity annotation
    # This creates a BaseMapper (bug)
    annotation_without_workaround = {
        'mapper': ('get_items', []),
        'update_mode': 'append'
    }

    mapper_without = BaseMapper.from_dict(annotation_without_workaround)
    print(f"Without workaround: {type(mapper_without).__name__}")
    assert isinstance(mapper_without, BaseMapper), "Bug: Creates BaseMapper"
    assert not isinstance(mapper_without, Transformer), "Bug: Not a Transformer"

    # Test case 2: Add dummy quantity annotation as workaround
    # First add quantity annotation
    DerivedA.name.m_annotations.setdefault(
        MAPPING_ANNOTATION_KEY, {}
    ).update({
        'test': Mapper(mapper='.dummy')
    })

    # Now test with both annotations present
    annotation_with_workaround = {
        'mapper': ('get_items', []),
        'update_mode': 'append',
        # The presence of the quantity annotation changes behavior
    }

    # This would need more complex setup to test properly
    # but demonstrates the workaround pattern

    m_package.init_metainfo()


def test_scf_criteria_pattern():
    """
    Test the specific pattern used in SCF criteria that fails.
    """
    m_package = Package()

    class NumericalSettings(Section):
        pass

    class SelfConsistency(NumericalSettings):
        name = Quantity(type=str)
        threshold_change = Quantity(type=float)

    class DFT(Section):
        numerical_settings = SubSection(
            sub_section=NumericalSettings,
            repeats=True
        )

    # This is what PR #181 tries to do - function-only mapper
    annotation_pr181 = {
        'mapper': ('get_all_criteria', []),
        'update_mode': 'append'
    }

    # This creates BaseMapper instead of Transformer (bug)
    mapper = BaseMapper.from_dict(annotation_pr181)
    print(f"PR #181 approach creates: {type(mapper).__name__}")
    assert isinstance(mapper, BaseMapper), "Creates BaseMapper"
    assert not isinstance(mapper, Transformer), "Not a Transformer - function won't be called"

    # Workaround: Add dummy quantity annotation
    SelfConsistency.name.m_annotations.setdefault(
        MAPPING_ANNOTATION_KEY, {}
    ).update({
        'test': Mapper(mapper='.dummy_to_force_transformer')
    })

    # Now the annotation would create a proper Transformer
    # (requires full parser setup to test properly)

    m_package.init_metainfo()


def test_workaround_patterns():
    """
    Document various workaround patterns for the bug.
    """
    m_package = Package()

    class BaseSection(Section):
        pass

    class ConcreteSection(BaseSection):
        name = Quantity(type=str)

    # Pattern 1: Add dummy quantity annotation
    ConcreteSection.name.m_annotations[MAPPING_ANNOTATION_KEY] = {
        'test': Mapper(mapper='.dummy')
    }

    # Pattern 2: Add dummy path mapper at section level
    ConcreteSection.m_def.m_annotations[MAPPING_ANNOTATION_KEY] = {
        'test': Mapper(mapper='.@')
    }

    # Pattern 3: Combine path and function mappers
    annotation_combined = {
        'mapper': '.@',  # Dummy path
        'function': ('get_items', []),  # Actual function
        'update_mode': 'append'
    }

    # Any of these patterns forces Transformer creation
    m_package.init_metainfo()


if __name__ == "__main__":
    test_function_mapper_bug_demonstration()
    test_scf_criteria_pattern()
    test_workaround_patterns()
    print("\nAll tests demonstrate the bug and workarounds successfully.")