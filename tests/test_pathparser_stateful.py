"""
Stateful property tests for PathParser set_data/get_data.

A hypothesis RuleBasedStateMachine drives interleaved set/read operations on a
single shared target dict and checks it against a plain nested-dict oracle after
every step. This catches cross-operation interaction bugs (stale interpreter
state, path-creation side effects) that single-shot @given tests cannot.

Scope: dict trees only, with a small fixed key alphabet so operations collide
and overwrite. Rules skip paths that would traverse through an existing scalar -
the framework's behavior there (writing at the highest existing level) is pinned
separately in test_set_through_scalar_writes_at_scalar below.
"""

import copy
from typing import Any

from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from nomad_file_parser.mapping_parser import PathParser

SEGMENTS = ('a', 'b', 'c')
path_strategy = st.lists(st.sampled_from(SEGMENTS), min_size=1, max_size=3).map(
    '.'.join
)
scalar_strategy = st.integers(min_value=0, max_value=99)
subtree_strategy = st.dictionaries(
    keys=st.sampled_from(SEGMENTS),
    values=scalar_strategy,
    min_size=1,
    max_size=3,
)


class PathParserMachine(RuleBasedStateMachine):
    """Model-based test: PathParser against a plain nested dict."""

    def __init__(self):
        super().__init__()
        self.parser = PathParser(parser_name='jmespath')
        self.target: dict = {}
        self.model: dict = {}

    def _prefixes_are_dicts(self, path: str) -> bool:
        """True if no proper prefix of path resolves to a scalar in the model."""
        node: Any = self.model
        for segment in path.split('.')[:-1]:
            if segment not in node:
                return True  # missing prefixes are created as dicts
            node = node[segment]
            if not isinstance(node, dict):
                return False
        return True

    def _model_set(self, path: str, value: Any) -> None:
        node = self.model
        segments = path.split('.')
        for segment in segments[:-1]:
            node = node.setdefault(segment, {})
        node[segments[-1]] = value

    def _model_get(self, path: str) -> Any:
        node: Any = self.model
        for segment in path.split('.'):
            if not isinstance(node, dict) or segment not in node:
                return None
            node = node[segment]
        return node

    @rule(path=path_strategy, value=scalar_strategy)
    def set_leaf(self, path: str, value: int):
        if not self._prefixes_are_dicts(path):
            return
        self.parser.set_data(path, self.target, value)
        self._model_set(path, value)

    @rule(path=path_strategy, subtree=subtree_strategy)
    def set_subtree(self, path: str, subtree: dict):
        if not self._prefixes_are_dicts(path):
            return
        self.parser.set_data(path, self.target, copy.deepcopy(subtree))
        self._model_set(path, copy.deepcopy(subtree))

    @rule(path=path_strategy)
    def read(self, path: str):
        assert self.parser.get_data(path, self.target) == self._model_get(path)

    @invariant()
    def target_matches_model(self):
        assert self.target == self.model


TestPathParserMachine = PathParserMachine.TestCase


@given(
    scalar=st.integers(min_value=0, max_value=99),
    value=st.integers(min_value=100, max_value=200),
)
def test_set_through_scalar_writes_at_scalar(scalar: int, value: int):
    """Characterization: setting a.b when a holds a scalar overwrites a itself.

    Traversal in set mode stops at the scalar (it cannot descend), and the set
    machinery then writes at the last reachable level. Pinned so a behavior
    change (e.g. raising or replacing the scalar with a dict) is noticed.
    """
    parser = PathParser(parser_name='jmespath')
    target = {'a': scalar}

    parser.set_data('a.b', target, value)

    assert target == {'a': value}
