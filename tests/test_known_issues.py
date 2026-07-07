"""
Deterministic reproductions of filed bugs, pinned as strict xfails.

One test per open issue on FAIRmat-NFDI/nomad-file-parser. Each asserts the
intended behavior, so it fails on the current code and flips to XPASS(strict)
when the bug is fixed, forcing removal of the marker. These are single repro
tests, not property suites: property coverage for the affected derived-parser
modules (text_parser, file_parser) is deliberately deferred.

The fourth filed bug, issue #9 (get_required_paths RecursionError), is pinned
in test_mapping_parser_properties.py::TestMapperStructure.
"""

import numpy as np
import pytest

from nomad_file_parser.file_parser import FileParser
from nomad_file_parser.text_parser import ParsePattern, Quantity


class MinimalFileParser(FileParser):
    """Smallest concrete FileParser: results are populated directly."""

    def parse(self, quantity_key: str | None = None, **kwargs):
        return self


# https://github.com/FAIRmat-NFDI/nomad-file-parser/issues/6
@pytest.mark.xfail(
    strict=True,
    reason='issue #6: ParsePattern.re_pattern is never compiled and __call__ '
    'has no return statement',
)
def test_parse_pattern_call_extracts_value():
    pattern = ParsePattern(key='energy', value='re_float')

    result = pattern('energy = 1.5\n', repeats=False)

    # Currently raises AttributeError ('str' object has no attribute 'search');
    # with a compiled pattern it would still return None (no return statement).
    assert result is not None


# https://github.com/FAIRmat-NFDI/nomad-file-parser/issues/7
@pytest.mark.xfail(
    strict=True,
    reason='issue #7: to_data sets self.dtype = None on conversion failure, '
    'degrading all subsequent conversions of the same Quantity',
)
def test_to_data_is_stateless():
    quantity = Quantity('q', r'q\s*=\s*(.+)', dtype=np.float64)

    before = quantity.to_data('1 2')
    assert before.dtype == np.float64

    quantity.to_data('x y')  # conversion failure must not affect later calls

    after = quantity.to_data('1 2')
    assert after.dtype == np.float64, (
        f'dtype degraded after unrelated failure: {after.dtype}'
    )


# https://github.com/FAIRmat-NFDI/nomad-file-parser/issues/8
@pytest.mark.xfail(
    strict=True,
    reason='issue #8: __getitem__ int branch is `return self[int]`, which '
    'matches neither branch and always returns None',
)
def test_getitem_int_returns_positional_result():
    parser = MinimalFileParser()
    parser['a'] = 1

    assert parser[0] == 1
