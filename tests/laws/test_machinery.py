"""Checks on the test machinery, not on the parser.

The generator must reach into the data: paths that stop at the first step
satisfy every law trivially. The joined path that the repetition laws use as
their reference must be standard JMESPath.
"""

import jmespath
from hypothesis import given, settings

from nomad_file_parser.mapping_parser import Path

from .strategies import paths
from .support import depth, hits_projection
from .trees import JOINED


def test_addresses_reach_into_the_data():
    """Guard on the generator: P(depth >= 2) >= 1/2 and P(projection hit) >= 1/5.

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


# The calculations of question 9: with leaves, an empty `s`, no `s`, steps
# without `e`, `s` holding `None`.
CALCULATIONS = {
    'c': [
        {'s': [{'e': 1}, {'e': 2}]},
        {'s': []},
        {},
        {'s': [{'x': 0}]},
        {'s': None},
        {'s': [{'e': 3}]},
    ]
}


def test_joined_path_is_jmespath():
    """Path(c[*].s[*].e).get_data(obj) = jmespath.search(c[*].s[*].e, obj) = [[1, 2], [], [], [3]].

    The reference of the repetition laws is standard JMESPath: a projection
    keeps `[]` and drops only `None` (question 9, closed).
    """
    expected = [[1, 2], [], [], [3]]
    assert jmespath.search(JOINED, CALCULATIONS) == expected
    assert Path(path=JOINED).get_data(CALCULATIONS) == expected
