import re

from nomad_file_parser import Quantity, TextParser


def parse_text(quantities: list[Quantity]) -> dict:
    text = '''other content
===header===
ITER 0 E -10
ITER 1 E -9
ITER 2 E -8
===footer===
other content'''
    parser = TextParser(quantities=quantities)
    parser._file_handler = text.encode()
    parser.parse()
    return parser._results

def test_regex_str():
    pattern = r'===header===\s*([\s\S]*?)\s*===footer==='
    expected = ['ITER', 0, 'E', -10.0, 'ITER', 1, 'E', -9.0, 'ITER', 2, 'E', -8.0]
    results = parse_text([Quantity('content', pattern)])
    assert results.get('content') == expected

def test_regex_compiled():
    pattern = re.compile(r'===header===\s*([\s\S]*?)\s*===footer===')
    expected = ['ITER', 0, 'E', -10.0, 'ITER', 1, 'E', -9.0, 'ITER', 2, 'E', -8.0]
    results = parse_text([Quantity('content', pattern)])
    assert results.get('content') == expected

def test_regex_multiline():
    pattern = re.compile(r'^(ITER.*)$', re.MULTILINE)
    expected = [['ITER', 0, 'E', -10.0], ['ITER', 1, 'E', -9.0], ['ITER', 2, 'E', -8.0]]
    results = parse_text([Quantity('content', pattern, repeats=True)])
    assert results.get('content') == expected
