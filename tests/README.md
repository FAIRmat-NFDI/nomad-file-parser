# Property-Based Test Suite

This suite verifies the mapping-parser framework through properties rather than
examples: algebraic laws (round-trip inverses, monoid identities, associativity,
idempotence), differential oracles against reference implementations, and
model-based stateful testing. Hypothesis generates the inputs, so each test
checks a relationship over hundreds of cases and shrinks failures to minimal
counterexamples. Example-based tests are used only where a single scenario is
the point (characterizations, API demonstrations).

## Running

Profiles are registered in `conftest.py` and selected via `HYPOTHESIS_PROFILE`:

| Profile | Examples per test | Use |
|---|---|---|
| `dev` (default) | 25 | local iteration |
| `ci` | 200, no deadline | pre-push and CI runs |
| `debug` | 25, verbose | diagnosing shrinking behavior |

```bash
uv run --package nomad-file-parser --extra dev pytest tests
HYPOTHESIS_PROFILE=ci uv run --package nomad-file-parser --extra dev pytest tests
```

Per-test `@settings` decorators override profile values where a test needs a
different budget (stress tests, expensive integration cases).

## Map

| File | Targets | Properties |
|---|---|---|
| `test_mapping_parser_properties.py` | `Path`, `Mapper`, update modes, `MetainfoParser` | get/set round-trip, merge monoid laws, `from_dict` homomorphism, update-mode semantics and idempotence, mode inheritance, serialization round-trips, mapper-tree structure (`get_required_paths`, `sort`) |
| `test_jmespath_extensions_properties.py` | `ParsedResult`, `TreeInterpreter`, `PathParser` | set/search inverse (simple, indexed, negative-index paths), slice broadcast and element-wise set, pop semantics, differential oracle against vanilla `jmespath` |
| `test_pathparser_stateful.py` | `PathParser` | model-based stateful testing: interleaved set/read operations against a plain nested-dict oracle with a full-state invariant per step |
| `test_nested_update_limitation.py` | `MetainfoParser.from_dict` | characterization of the depth-2 update limitation against a manual-transformer baseline |
| `test_mapping_annotation_constraints.py` | mapping annotations | serialization constraints, lambda support, declarative patterns |
| `test_array_iteration_patterns.py` | `MetainfoParser.from_dict` | example-based demonstration of array iteration and the `repeats=True` requirement |

Shared strategies live in `strategies.py`; `conftest.py` also applies the
`ClassicLogger` monkeypatch that unblocks instantiation of `MappingParser`
subclasses (see the comment there for the root cause).

## Known-quirk registry

Known bugs and undecided semantics are active tests marked
`xfail(strict=True)`, never comments or skips. Each carries a pinned
`@example` counterexample so the failure is deterministic. When the underlying
behavior is fixed, the test flips to `XPASS(strict)` and fails the suite,
forcing removal of the marker and turning the test into a regression guard.

| Test | Behavior pinned | Issue |
|---|---|---|
| `test_get_required_paths_prefix_closure` | `get_required_paths()` raises `RecursionError`: `BaseMapper.__iter__` yields self for leaf mappers | [#9](https://github.com/FAIRmat-NFDI/nomad-file-parser/issues/9) |
| `test_path_format_equivalence` | `set_data` ignores the parent context of a relative `Path` | pending |
| `test_append_mode_prepends_existing_to_lists` | append mode replaces existing list elements with empty dicts | pending |
| `test_merge_commutative_disjoint_keys` | first-merged keys are stored with a leading dot, breaking commutativity | pending |
| `test_cardinality_preservation` | `from_dict` drops elements whose fields are all falsy, not only all-None | pending |
| `test_polymorphic_type_preservation` | `from_dict` ignores `m_def`, instantiating the base section type | pending |
| `test_end_to_end_cardinality_annotation_driven` | annotation-driven pipeline loses source-list cardinality | pending |
| `test_transformer_list_creates_instances` | list-returning transformer creates no instances | pending |
| `test_update_mode_with_instances` | `replace` with an empty incoming list keeps existing instances | pending |

The last four predate the 2026-07 suite extension and track drift against the
nomad-lab version in the development workspace rather than regressions in this
package.

## Conventions

New property tests should draw shared input shapes from `strategies.py` and add
new composite strategies there when they are reusable. Deliberate framework
deviations (for example, field access on a list resolving to the last element)
are pinned with passing characterization tests so that a behavior change is
noticed, while genuine defects follow the strict-xfail pattern above with an
entry in the registry and, once filed, a link to the upstream issue.
