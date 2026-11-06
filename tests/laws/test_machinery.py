"""Checks on the test machinery, not on the parser.

The generator must reach into the data: paths that stop at the first step
satisfy every law trivially.
"""

from hypothesis import given, settings

from nomad_file_parser.mapping_parser import Path

from .strategies import at_filter, paths
from .support import depth, hits_projection


def test_addresses_reach_into_the_data():
    """Guard on the generator: P(depth ≥ 2) ≥ 1/2 and P(projection hit) ≥ 1/5.

    Paths that stop at the first step satisfy every law as None == None;
    this fails when the generator drifts back to such paths.
    """
    depths, hits = [], []

    @settings(max_examples=300, derandomize=True, database=None)
    @given(paths())
    def sample(case):
        obj, path = case
        depths.append(depth(obj, path))
        hits.append(hits_projection(obj, path))

    sample()
    assert sum(d >= 2 for d in depths) / len(depths) >= 0.5
    assert sum(hits) / len(hits) >= 0.2


def test_filters_select_elements():
    """Guard on the filter generator: P(the filter selects at least one element) ≥ 1/3.

    A filter that never matches gives [] everywhere, and the filter laws hold
    on it trivially.
    """
    selects = []

    @settings(max_examples=300, derandomize=True, database=None)
    @given(at_filter())
    def sample(case):
        obj, p0, condition, _ = case
        selected = Path(path=p0.dot(str(condition))).get_data(obj)
        selects.append(bool(selected) and isinstance(selected, list))

    sample()
    assert sum(selects) / len(selects) >= 1 / 3
