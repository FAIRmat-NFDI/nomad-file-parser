"""
Test whether quantity annotations can use source with transformer tuple.

This tests the pattern suggested in APPEND_EACH_AND_FRAMEWORK_LIMITATIONS.md
as a potential workaround for section-level transformers.

Pattern being tested:
    DFT.numerical_settings.m_annotations['test'] = Mapper(
        source=('get_all_criteria', []),  # Function as SOURCE
        mapper=[
            {'mapper': '.name', 'target': '.name'},
            {'mapper': '.threshold', 'target': '.threshold'}
        ]
    )
"""

import pytest
from nomad.metainfo import MSection, Quantity, SubSection
from nomad.datamodel.metainfo.annotations import Mapper
from nomad_file_parser.mapping_parser import (
    MAPPING_ANNOTATION_KEY,
    MappingParser,
)


# Test schema
class SelfConsistency(MSection):
    """Convergence criterion."""
    name = Quantity(type=str)
    threshold = Quantity(type=float)


class DFT(MSection):
    """DFT method."""
    numerical_settings = SubSection(sub_section=SelfConsistency, repeats=True)


# Test parser
class SourceTransformerParser(MappingParser):
    """Parser to test source with transformer."""

    def get_all_criteria(self):
        """Return list of criterion dicts."""
        return [
            {'name': 'energy_change', 'threshold': 1e-6},
            {'name': 'density_change', 'threshold': 1e-5},
            {'name': 'eigenvalue_change', 'threshold': 1e-4},
        ]


def test_source_with_transformer_tuple():
    """Test if source parameter accepts transformer tuple."""

    # Pattern 1: source as transformer tuple (simple)
    try:
        mapper = Mapper(
            source=('get_all_criteria', []),  # Transformer as source
            update_mode='append_each'
        )
        print("✓ Mapper accepts source as transformer tuple (simple)")
        pattern1_works = True
    except Exception as e:
        print(f"✗ Mapper rejects source as transformer tuple: {e}")
        pattern1_works = False

    # Pattern 2: source as string path (known to work)
    try:
        mapper = Mapper(
            source='@.criteria',
            update_mode='append_each'
        )
        print("✓ Mapper accepts source as string path")
        pattern2_works = True
    except Exception as e:
        print(f"✗ Mapper rejects source as string path: {e}")
        pattern2_works = False

    # Pattern 3: source transformer with mapper path
    try:
        mapper = Mapper(
            source=('get_all_criteria', []),
            mapper='.',  # Simple path mapper
            update_mode='append_each'
        )
        print("✓ Mapper accepts source transformer with mapper path")
        pattern3_works = True
    except Exception as e:
        print(f"✗ Mapper rejects source transformer with mapper: {e}")
        pattern3_works = False

    # We know pattern 2 works
    assert pattern2_works, "String path source should work"

    # Return whether pattern 1 or 3 works
    return pattern1_works or pattern3_works


def test_source_transformer_annotation():
    """Test if source transformer can be used in annotations."""

    # Try to add annotation with source transformer (simple pattern)
    try:
        DFT.numerical_settings.m_annotations.setdefault(
            MAPPING_ANNOTATION_KEY, {}
        ).update({
            'test': Mapper(
                source=('get_all_criteria', []),
                mapper='.',  # Simple path
                update_mode='append_each'
            )
        })
        print("✓ Annotation with source transformer set successfully")
        success = True
    except Exception as e:
        print(f"✗ Failed to set annotation: {e}")
        success = False

    # Check that annotation was stored
    if success:
        annotation = DFT.numerical_settings.m_annotations.get(MAPPING_ANNOTATION_KEY, {}).get('test')
        if annotation:
            # Check what attributes the Mapper has
            attrs = [attr for attr in dir(annotation) if not attr.startswith('_')]
            print(f"✓ Annotation stored")
            print(f"  Available attributes: {', '.join(attrs[:10])}")  # Show first 10
            print(f"  mapper attribute: {annotation.mapper}")
            if hasattr(annotation, 'update_mode'):
                print(f"  update_mode: {annotation.update_mode}")
        else:
            print("✗ Annotation not found after setting")
            success = False

    return success


def test_source_vs_mapper_with_function():
    """Compare source vs mapper for function transformers."""

    results = {}

    # Test 1: Function in mapper (known pattern)
    try:
        mapper1 = Mapper(
            mapper=('get_all_criteria', []),
            update_mode='append_each'
        )
        results['mapper_function'] = 'accepted'
    except Exception as e:
        results['mapper_function'] = f'rejected: {e}'

    # Test 2: Function in source
    try:
        mapper2 = Mapper(
            source=('get_all_criteria', []),
            update_mode='append_each'
        )
        results['source_function'] = 'accepted'
    except Exception as e:
        results['source_function'] = f'rejected: {e}'

    # Test 3: Function in mapper with nested mappers
    try:
        mapper3 = Mapper(
            mapper=('get_all_criteria', []),
            target='.',
            update_mode='append_each'
        )
        results['mapper_function_with_target'] = 'accepted'
    except Exception as e:
        results['mapper_function_with_target'] = f'rejected: {e}'

    # Test 4: Function in source with nested mappers
    try:
        mapper4 = Mapper(
            source=('get_all_criteria', []),
            mapper=[{'mapper': '.name', 'target': 'name'}],
            update_mode='append_each'
        )
        results['source_function_with_mappers'] = 'accepted'
    except Exception as e:
        results['source_function_with_mappers'] = f'rejected: {e}'

    print("\nPattern Acceptance Results:")
    for pattern, result in results.items():
        symbol = "✓" if result == 'accepted' else "✗"
        print(f"  {symbol} {pattern}: {result}")

    return results


if __name__ == "__main__":
    print("=" * 60)
    print("TESTING SOURCE TRANSFORMER PATTERN")
    print("=" * 60)

    print("\n1. Testing Mapper Construction:")
    pattern1_works = test_source_with_transformer_tuple()

    print("\n2. Testing Pattern Variations:")
    results = test_source_vs_mapper_with_function()

    if pattern1_works:
        print("\n3. Testing Annotation Storage:")
        execution_works = test_source_transformer_annotation()
    else:
        print("\n3. Skipping annotation test (pattern not accepted)")
        execution_works = False

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if pattern1_works and execution_works:
        print("✓ SOURCE TRANSFORMER PATTERN WORKS!")
        print("  This is a viable workaround for section-level transformers")
    elif pattern1_works:
        print("⚠ Source accepts transformers but execution may not work")
        print("  Further investigation needed")
    else:
        print("✗ SOURCE TRANSFORMER PATTERN DOES NOT WORK")
        print("  Need to proceed with Phase 2 (framework fix)")
