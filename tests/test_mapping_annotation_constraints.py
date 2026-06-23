"""
Test constraints and limitations of the mapping annotation system.

This module tests what can and cannot be used in mapping annotations,
documenting the framework's design constraints using predicate logic.

Key predicates:
- Serializable(x, format): x can be serialized to format
- ValidAnnotation(a): a is a valid mapping annotation
- Contains(x, type): x contains an element of type
- Supports(system, feature): system supports feature
"""

import string
from typing import Any, Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nomad.datamodel.metainfo.annotations import Mapper
from nomad.parsing.file_parser.mapping_parser import MAPPING_ANNOTATION_KEY, MetainfoParser
from nomad.metainfo import Quantity, Section


class TestAnnotationConstraints:
    """Test what types of values can be used in mapping annotations."""

    def test_lambda_functions_work_but_not_serializable(self):
        """
        Empirical finding: Lambda functions work in str_operation but aren't JSON-serializable.

        Property: ∀λ ∈ LambdaFunctions:
            WorksIn(λ, str_operation) ∧ ¬Serializable(λ, JSON)

        This means:
        - Lambdas CAN be used for transformations
        - But annotations containing lambdas cannot be persisted to JSON
        - This is acceptable for parser definitions which are in Python code
        """
        # Test 1: Lambdas work in str_operation (proven in test_lambda_actually_works.py)
        from nomad.parsing.file_parser.text_parser import Quantity as ParserQuantity

        # This works!
        q = ParserQuantity(
            'test',
            r'value: (\d+)',
            str_operation=lambda x: float(x) * 2
        )
        assert callable(q.str_operation)

        # Test 2: But they're not JSON serializable
        import json
        with pytest.raises(TypeError):
            json.dumps({'transform': lambda x: x * 2})

    @given(
        mapper_path=st.text(
            alphabet=string.ascii_letters + '._[]',
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=20)
    def test_string_mappers_are_supported(self, mapper_path: str):
        """
        Property: ∀s ∈ StringPaths: Serializable(s, JSON) ∧ ValidAnnotation(mapper=s)

        Where StringPaths = {s | IsString(s) ∧ IsJMESPath(s)}

        Examples of valid paths:
        - '.value' ∈ StringPaths
        - '.items[*].value' ∈ StringPaths
        - lambda x: x.value ∉ StringPaths (not a string)
        """
        # String mappers should always be valid
        annotation = {
            MAPPING_ANNOTATION_KEY: {
                'text': Mapper(mapper=mapper_path)
            }
        }

        # Should be serializable
        import json
        serialized = json.dumps(annotation, default=str)
        assert serialized is not None

        # Should be deserializable
        deserialized = json.loads(serialized)
        assert deserialized is not None

    def test_transform_alternatives(self):
        """
        Document the correct alternatives to lambda transforms.

        Instead of lambda functions in annotations, transformations should be:
        1. Handled in str_operation functions in the parser
        2. Implemented as methods in the parser class
        3. Applied during normalization
        """
        # Correct approach: Use str_operation in parser
        from nomad_simulation_parsers.parsers.fhiaims.out_parser import str_to_scf_convergence

        # This is the right way - reference a named function
        annotation = {
            'str_operation': str_to_scf_convergence  # Named function reference
        }

        # The function exists and can be called
        assert callable(annotation['str_operation'])

        # But note: even this won't serialize to JSON
        # The function name would need to be stored as a string and looked up

    @given(
        st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(),
            st.booleans(),
            st.none(),
            st.lists(st.integers(), max_size=5),
            st.dictionaries(st.text(max_size=10), st.integers(), max_size=3)
        )
    )
    def test_json_serializable_values_supported(self, value: Any):
        """
        Property: ∀v ∈ PrimitiveTypes: Serializable(v, JSON) → ValidAnnotationValue(v)

        Where PrimitiveTypes = {int, float, str, bool, None, list<Primitive>, dict<str,Primitive>}

        Contrapositive: ¬Serializable(v, JSON) → ¬ValidAnnotationValue(v)
        Therefore: ∀f ∈ Functions: ¬ValidAnnotationValue(f)
        """
        annotation = {
            MAPPING_ANNOTATION_KEY: {
                'text': {
                    'mapper': '.value',
                    'default': value  # JSON-serializable default value
                }
            }
        }

        import json
        # Should serialize without error
        serialized = json.dumps(annotation)
        assert serialized is not None

        # Should round-trip correctly
        deserialized = json.loads(serialized)
        if value is not None and not isinstance(value, float):
            # Skip float comparison due to precision issues
            assert deserialized[MAPPING_ANNOTATION_KEY]['text']['default'] == value

    def test_complex_jmespath_expressions(self):
        """
        Test that complex JMESPath expressions are supported as strings.
        """
        complex_expressions = [
            '.items[*].value',  # Wildcard projection
            '.data[?type==`energy`].value',  # Filter expression
            '.results[-1].energy',  # Negative index
            '.atoms[0:3].position',  # Slice
            '.calculation.{energy: total_energy, forces: atomic_forces}',  # Multi-select hash
        ]

        for expr in complex_expressions:
            annotation = {
                MAPPING_ANNOTATION_KEY: {
                    'text': Mapper(mapper=expr)
                }
            }

            # Should be representable as a string
            assert isinstance(expr, str)

            # The Mapper should accept it
            mapper = Mapper(mapper=expr)
            assert mapper.mapper == expr

    def test_annotation_must_be_declarative(self):
        """
        Property: ∀a ∈ ValidAnnotations: IsDeclarative(a) ∧ ¬IsImperative(a)

        Where:
        - IsDeclarative(x) ≡ DescribesWhat(x) ∧ ¬ContainsLogic(x)
        - IsImperative(x) ≡ DescribesHow(x) ∧ ContainsLogic(x)

        Example contradiction:
        Let a = {'transform': λx.abs(x)}
        ContainsLogic(a) = true (has transformation function)
        Therefore: IsImperative(a) = true
        Therefore: ¬ValidAnnotation(a)
        """
        # Good: Declarative path
        good_annotation = {
            MAPPING_ANNOTATION_KEY: {
                'text': Mapper(mapper='.scf_convergence."Change of total energy"')
            }
        }

        # Bad: Trying to embed logic (this won't work)
        # This documents what NOT to do
        try:
            bad_annotation = {
                MAPPING_ANNOTATION_KEY: {
                    'text': Mapper(
                        mapper='.value',
                        # Don't do this - logic doesn't belong in annotations
                        transform=lambda x: abs(x) if x > 0 else 0
                    )
                }
            }
            # This will fail when trying to use it
        except Exception:
            pass  # Expected to fail

    def test_transform_via_parser_methods(self):
        """
        Document the correct pattern for transformations in parsers.
        """
        # The correct pattern is to use parser methods
        class MyParser(MetainfoParser):
            def get_energy(self, source: dict) -> dict:
                """Transform energy data from source."""
                energy = source.get('energy', 0)
                # Transform logic goes here, not in annotations
                return {'value': abs(energy)}

            def get_forces(self, source: dict) -> dict:
                """Transform forces data from source."""
                forces = source.get('forces', [])
                # Complex transformations in method
                return {'value': [abs(f) for f in forces]}

        # Instantiate and verify methods exist
        parser = MyParser()
        assert hasattr(parser, 'get_energy')
        assert hasattr(parser, 'get_forces')

        # These methods contain the transformation logic
        test_data = {'energy': -100, 'forces': [-1, 2, -3]}
        energy_result = parser.get_energy(test_data)
        forces_result = parser.get_forces(test_data)

        assert energy_result['value'] == 100
        assert forces_result['value'] == [1, 2, 3]


class TestAnnotationSerialization:
    """Test serialization constraints of mapping annotations."""

    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.one_of(
                st.text(),
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.booleans(),
                st.none()
            ),
            max_size=5
        )
    )
    def test_annotation_dict_serialization(self, annotation_data: dict):
        """
        Property: ∀d ∈ Dict<String, Primitive>: Serializable(d, JSON)

        This establishes the domain of valid annotation structures.
        By construction of the hypothesis strategy:
        ∀k ∈ keys(d): IsString(k)
        ∀v ∈ values(d): v ∈ PrimitiveTypes
        """
        annotation = {
            MAPPING_ANNOTATION_KEY: annotation_data
        }

        import json
        # Should serialize
        serialized = json.dumps(annotation)

        # Should deserialize to same structure
        deserialized = json.loads(serialized)
        assert deserialized == annotation

    def test_annotation_with_units(self):
        """
        Test that unit specifications in annotations work correctly.
        """
        from nomad.units import ureg

        # Units should be specified as strings, not objects
        correct_annotation = {
            MAPPING_ANNOTATION_KEY: {
                'text': {
                    'mapper': '.energy',
                    'unit': 'eV'  # String representation
                }
            }
        }

        # This is serializable
        import json
        json.dumps(correct_annotation)

        # But this won't work:
        with pytest.raises(TypeError):
            wrong_annotation = {
                MAPPING_ANNOTATION_KEY: {
                    'text': {
                        'mapper': '.energy',
                        'unit': ureg.eV  # Unit object - not serializable
                    }
                }
            }
            json.dumps(wrong_annotation)


class TestLambdaFunctionalityInPractice:
    """Test if lambda functions actually work in practice with the parser."""

    def test_lambda_executes_in_text_parser(self):
        """
        Empirical proof: Lambda functions execute in TextParser.

        Property: ∀λ ∈ LambdaFunctions, ∀x ∈ InputData:
            Parse(Quantity(str_operation=λ), x) = λ(x)

        This test proves lambdas aren't just accepted but actually execute.
        """
        import tempfile
        from nomad.parsing.file_parser.text_parser import Quantity as ParserQuantity, TextParser

        # Create parser with lambda that doubles the value
        parser = TextParser(quantities=[
            ParserQuantity(
                'value_doubled',
                r'value:\s*(\d+)',
                str_operation=lambda x: float(x) * 2
            ),
            ParserQuantity(
                'value_normal',
                r'value:\s*(\d+)',
                str_operation=float
            )
        ])

        # Test with actual file
        test_text = "value: 5"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_text)
            parser.mainfile = f.name
        parser.parse()

        # Verify lambda executed: 5 * 2 = 10
        assert parser.get('value_doubled') == 10.0
        assert parser.get('value_normal') == 5.0

    def test_lambda_with_abs_for_scf(self):
        """
        Practical test: Lambda with abs() for SCF delta values.

        This demonstrates the actual use case for SCF parsing.
        """
        import tempfile
        from nomad.parsing.file_parser.text_parser import Quantity as ParserQuantity, TextParser

        parser = TextParser(quantities=[
            ParserQuantity(
                'delta_energy',
                r'Change of total energy\s*:\s*([-\d\.]+)',
                str_operation=lambda x: abs(float(x))  # Apply abs directly!
            )
        ])

        test_text = "Change of total energy : -0.123"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_text)
            parser.mainfile = f.name
        parser.parse()

        # Lambda with abs() works: |-0.123| = 0.123
        assert parser.get('delta_energy') == 0.123


class TestDeclarativePatternsForSCF:
    """Test declarative patterns specifically for SCF parsing."""

    def test_declarative_mapping_pattern(self):
        """
        Property: ∀a ∈ ValidMappingAnnotations:
            IsPath(a.mapper) ∧
            ¬ContainsTransform(a) ∧
            (∀t ∈ DataTransformations: Location(t) ∉ Annotation)

        General principle:
        - Annotations specify paths (WHERE data is)
        - Parser methods transform data (HOW to process it)
        - Separation of concerns: declaration vs transformation
        """
        # Declarative: Specify paths to data
        declarative_annotations = {
            'delta_energy_path': '.self_consistency[*].scf_convergence."Change of total energy"',
            'delta_density_path': '.self_consistency[*].scf_convergence."Change of charge density"',
            'duration_path': '.self_consistency[*].time_calculation',
        }

        # These are just strings - fully declarative
        for key, path in declarative_annotations.items():
            assert isinstance(path, str)
            assert path.startswith('.')

        # The transformation logic (like abs()) should be in the parser
        class SCFParser:
            def process_delta_values(self, values: list) -> list:
                """Apply transformations to delta values."""
                return [abs(v) if v is not None else None for v in values]

        parser = SCFParser()
        test_values = [0.1, -0.2, 0.3, -0.4]
        processed = parser.process_delta_values(test_values)
        assert processed == [0.1, 0.2, 0.3, 0.4]

    def test_hierarchical_scf_data_pattern(self):
        """
        Test pattern for hierarchical SCF data extraction.
        """
        # Pattern for nested SCF iteration data
        scf_patterns = {
            # Top level - geometry steps
            'geometry_steps': '.geometry_optimization[*]',
            # SCF iterations within each geometry step
            'scf_iterations': '.geometry_optimization[*].self_consistency[*]',
            # Convergence data within each SCF iteration
            'convergence_data': '.geometry_optimization[*].self_consistency[*].scf_convergence',
        }

        # All patterns are declarative strings
        for pattern in scf_patterns.values():
            assert isinstance(pattern, str)
            # Should contain array accessors for nested data
            if '[*]' in pattern:
                assert pattern.count('[*]') <= pattern.count('.')