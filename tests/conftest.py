"""
Shared test configuration: ClassicLogger monkeypatch and hypothesis profiles.
"""

import os

from hypothesis import Verbosity, settings

# =============================================================================
# Monkeypatch ClassicLogger to Fix ABC Interaction
# =============================================================================
#
# ISSUE: ClassicLogger's __getattr__ returns a lambda for ANY attribute access,
# including Python's special __isabstractmethod__ attribute used by ABC machinery.
# This causes Python to mark 'logger' as an abstract method, preventing instantiation
# of MappingParser subclasses (MetainfoParser, HDF5Parser, XMLParser).
#
# ROOT CAUSE: In nomad/utils/__init__.py, ClassicLogger defines:
#     def __getattr__(self, key):
#         return lambda *args, **kwargs: self.__log(key, *args, **kwargs)
#
# When Python's ABC checks MappingParser.logger.__isabstractmethod__, it gets a
# truthy lambda instead of AttributeError, marking logger as abstract.
#
# SOLUTION: Monkeypatch __getattr__ to raise AttributeError for __isabstractmethod__.
# Applied here once at conftest import so every test module sees the fix.
#
# See: mapping-parser-framework-feedback.md for detailed analysis.
#
from nomad.utils import ClassicLogger

_original_getattr = ClassicLogger.__getattr__


def _fixed_getattr(self, key):
    """Fixed __getattr__ that doesn't return lambda for __isabstractmethod__."""
    if key == '__isabstractmethod__':
        raise AttributeError(key)
    return _original_getattr(self, key)


ClassicLogger.__getattr__ = _fixed_getattr


# =============================================================================
# Hypothesis Profiles
# =============================================================================
#
# Select with HYPOTHESIS_PROFILE=ci|dev|debug (default: dev).
# Per-test @settings decorators still override profile values.

settings.register_profile('ci', max_examples=200, deadline=None, print_blob=True)
settings.register_profile('dev', max_examples=25)
settings.register_profile('debug', max_examples=25, verbosity=Verbosity.verbose)

settings.load_profile(os.environ.get('HYPOTHESIS_PROFILE', 'dev'))
