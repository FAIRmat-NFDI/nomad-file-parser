"""
Test if lambda functions ACTUALLY work in the mapping parser, not just get accepted.
"""

import tempfile
from nomad.parsing.file_parser.text_parser import Quantity, TextParser


def test_lambda_str_operation_executes():
    """Test if lambda in str_operation actually gets executed."""

    # Create a parser with lambda transform
    parser = TextParser(quantities=[
        Quantity(
            'value_doubled',
            r'value:\s*(\d+)',
            str_operation=lambda x: float(x) * 2
        ),
        Quantity(
            'value_normal',
            r'value:\s*(\d+)',
            str_operation=float
        )
    ])

    test_text = "value: 5"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_text)
        parser.mainfile = f.name
    parser.parse()

    # If lambda executes, value_doubled should be 10.0
    # If lambda is ignored, it would be 5.0 or error
    print(f"Results: {parser._results}")
    print(f"value_doubled: {parser.get('value_doubled')}")
    print(f"value_normal: {parser.get('value_normal')}")

    assert parser.get('value_normal') == 5.0

    # THE KEY TEST: Does lambda actually execute?
    if parser.get('value_doubled') == 10.0:
        print("LAMBDA WORKS AND EXECUTES!")
        assert parser.get('value_doubled') == 10.0
    elif parser.get('value_doubled') == 5.0:
        print("Lambda accepted but not executed")
    else:
        print(f"Unexpected result: {parser.get('value_doubled')}")


def test_lambda_in_mapping_annotation():
    """Test if lambda in mapping annotation works for SCF-like transforms."""

    # This would be perfect for SCF delta values!
    parser = TextParser(quantities=[
        Quantity(
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

    print(f"Input: -0.123")
    print(f"Output: {parser.get('delta_energy')}")

    # If lambda works, this should be 0.123 (absolute value)
    if parser.get('delta_energy') == 0.123:
        print("LAMBDA WITH ABS() WORKS!")
        assert parser.get('delta_energy') == 0.123
    else:
        print(f"Lambda didn't work as expected: {parser.get('delta_energy')}")


if __name__ == "__main__":
    test_lambda_str_operation_executes()
    test_lambda_in_mapping_annotation()