"""Checks on the test machinery, not on the parser.

The generator must reach into the data, and the reference evaluation `run`
must agree with JMESPath on the fragment it covers.
"""

import jmespath
from hypothesis import given, settings

from .reference import depth, hits_projection, run
from .strategies import addresses, perturbed, pipelines, render_pipeline
from .test_traversal import pinned


def test_addresses_reach_into_the_data():
    """Guard on the generator: P(depth ≥ 2) ≥ 1/2 and P(projection hit) ≥ 1/5.

    Paths that stop at the first step satisfy every law as None == None;
    this fails when the generator drifts back to such paths.
    """
    depths, hits = [], []

    @settings(max_examples=300, derandomize=True, database=None)
    @given(perturbed(addresses()))
    def sample(case):
        source, chain = case
        depths.append(depth(source, chain))
        hits.append(hits_projection(source, chain))

    sample()
    assert sum(d >= 2 for d in depths) / len(depths) >= 0.5
    assert sum(hits) / len(hits) >= 0.2


@given(pipelines(min_index=-3))
@pinned
def test_reference_matches_jmespath(case):
    """run(p)(x) = jmespath(p)(x): the defining equations, without the field-on-list rule.

    Compares `run` with `jmespath.search` on this fragment, negative indices
    included, so that the equations tested on `Path` are those of JMESPath
    plus that one rule.
    """
    source, pipeline = case
    expected = jmespath.search(render_pipeline(pipeline), source)
    assert run(pipeline, source) == expected
