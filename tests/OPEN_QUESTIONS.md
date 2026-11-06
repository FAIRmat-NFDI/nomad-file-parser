# Open questions on path semantics

Behaviours found while writing the law tests in `tests/laws/` where it is not clear whether they are intended.
Each answer decides whether the matching test pins current behaviour as a law or becomes a strict xfail.
All examples were run on `develop` at `97b4d54`.

## Paths (`Path.get_data`)

1. **Field on a list takes the last element.**
   `a.x` on `{'a': [{'x': 1}, {'x': 2}]}` gives `2`; JMESPath gives `None` (`visit_field`, `value = value[-1]`).
   Is this deliberate, e.g. so that one path reads both a single and a repeated XML element?
2. **Negative index past the start of a list.**
   In search mode, `a[-3]` on `{'a': [1, 2]}` returns `1` and changes the source to `{'a': [1, 2, {}]}`; `a[-1]` on `{'a': []}` returns `{}` and leaves `{'a': [{}]}`.
   The guard in `visit_index` only covers positive overflow, so the set-mode padding runs on a read.
   In set mode, `a[-3] = 'x'` gives `['x', 2, {}]`: element 0 is overwritten and the list is padded at the end.
   Should a read return `None` here and leave the source untouched, and is the set-mode result the intended one?
3. **Slice past the end of a list.**
   `a[0:5]` and `a[-5:]` on a two-element list give `None`; JMESPath clamps the bounds and returns both elements (`visit_slice` returns `None` in search mode once a bound exceeds the length).
4. **Relative prefix inside a function call.**
   The `Mapper` annotation docstring's example `length(.array.set.set)` gives `None`: the leading `.` is stripped only at the start of the path or after whitespace, so it stays inside the call, the expression does not parse, and the error is swallowed.
   Should relative paths work inside functions, or should the docstring change?
5. **Bare `.`** gives `None` (it becomes the empty expression).
   Should it mean the same as `.@`, or is it invalid?
6. **`default=`** is returned only when the expression fails to parse, not when the path is missing: `a.x` on `{'a': {}}` gives `None` even with `default='S'`.

## Mapper tree (`Mapper.get_data`)

7. **List source without `indices`.**
   A mapper whose source resolves to a list keeps only the first non-empty element when `indices` is not set: source `a` with child `.x` on `{'a': [{'x': 1}, {'x': 2}]}` gives `{'A': {'X': 1}}`.
   Is that how a non-repeating section is meant to read a repeated source?
8. **Dropped positions.**
   With `indices` set, elements whose children are all empty are dropped and the later ones move up: nested sources `a` → `.y` → `.z` on `[{'y': {'z': 3}}, {'x': 2}, {'y': {'z': 4}}]` give `[{'Y': {'Z': 3}}, {'Y': {'Z': 4}}]`, without a record that element 1 was skipped.
   Should repeating subsections keep their positions, e.g. to stay aligned with a sibling quantity read by index?

Questions 9 to 12 were run on `test/pbt-path-laws` at `38ed0c8`, on the source `{'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': [{'e': 3}]}]}` and variants of it.

9. **Nested sections versus the joined path.**
   Two repeating mappers, `c` (`indices=[]`) with child `.s` (`indices=[]`) and quantity `.e`, give the nesting of the joined path `c[*].s[*].e` as long as every element has data.
   They differ once an element is empty: the path keeps `[]` for an element whose `s` is an empty list and drops only `None` (missing `s`), whereas the mapper drops both (question 8).
   Is the joined path the intended reference for the shape of nested sections, up to the dropping of empty elements?
10. **A projection in a source path does not nest.**
   A single repeating mapper with source `c[*].s` or `c[*].s[*]` (`indices=[]`) and child `.e` gives `[{'E': 1}, {'E': 3}]`: one section per element of `c`, with each inner list reduced to its first element.
   The path `c[*].s[*].e` gives `[[1, 2], [3]]`.
   The reduction takes the first element, while a field step on a list in `Path` takes the last (question 1).
   Should a doubly projected source be flattened into one section per leaf, rejected, or kept as is, and should the first-versus-last choice agree with `Path`?
11. **`indices=[]` means "all elements, as a list".**
   An empty list disables the filter (`if indices and n not in indices`) while still making the result a list (`mapper.indices is None` is false), so it is the only way to request every element of a repeating section.
   The order of `indices` is ignored (`[1, 0]` gives source order) and duplicates collapse (`[0, 0]` gives one element).
   Is `[]` the intended spelling of "all", and should the order of `indices` matter?
12. **Negative entries in `indices` match nothing.**
   `indices=[-1]` gives `{}`, since the source positions `n` compared against it are never negative, whereas the path step `[-1]` selects the last element.
   An out-of-range entry (`[5]`) also gives `{}` silently.
   Should negative entries count from the end, as in paths, or be rejected?

## Polymorphic subsections (`MetainfoParser`)

Questions 13 to 18 were run on `test/pbt-path-laws` at `99ccf35`, on an unannotated base `Shape` with the subclasses `Circle` (`radius`), `Square` (`side`) and `Triangle` (`height`) under the repeating subsection `Drawing.shapes`.

13. **Merging across subclasses keeps the first type.**
   Two passes with `update_mode='merge'`, `Circle` under `k1` and then `Square` under `k2`, on `{radius: 1, side: 2}` give `[Circle(radius=1)]`: the second pass aligns `Square` with the existing element at position 0, the first type wins and `side` is lost without a warning.
   Should a merge at a position whose `m_def` differs append instead, fail, or keep this behaviour?
14. **An unresolvable `m_def` falls back to the base.**
   In `from_dict`, an element whose `m_def` names no section of the hierarchy (unknown, or a section outside it) is built as the declared base type.
   With a base field (`name`) it survives as a `Shape`; with a subclass field it is dropped as empty. Neither case is logged.
   Should an unresolvable `m_def` be reported, or rejected?
15. **A field of another subclass is dropped silently.**
   `{m_def: Square, radius: 1}` gives no element: `radius` is not a `Square` quantity, `m_set` fails inside a bare `except`, and the element is dropped as empty.
   Should a value that does not fit the resolved type be reported?
16. **Scalar update modes all overwrite.**
   A second pass replaces a scalar (`Drawing.title`) under `append`, `merge` and `replace` alike, whereas the `Path.set_data` docstring describes `append` as "keep existing data if present" and the dictionary-level code keeps the current scalar under `merge`.
   Which is intended at the archive level, and should the docstring change?
17. **Falsy-only subsections are dropped.**
   A subsection whose only value is falsy (`Circle(radius=0.0)`, `Shape(name='')`) is treated as empty by `from_dict` (`or v` in the emptiness check) and removed, while the `Mapper` keeps falsy values (`is_not_value` compares with `None`, `[]`, `{}`).
   Is this intended, or should the emptiness check match the mapper's?
18. **A later pass reuses a misaligned element and reassigns its `m_def`.**
   Pass `k1` maps `Circle` and `Triangle`, pass `k2` maps nothing, both with `append`, on `{height: 1}`.
   Pass 1 drops the empty `Circle` from the archive but keeps `{m_def: Circle}` at position 0 of the parser's intermediate data, where the archive now holds the `Triangle`.
   Pass 2 replays the data by position, reuses that `Triangle` instance and sets its `m_def` to `Circle` (`sub_section.m_def = section_def`), so the result is `[Triangle with m_def Circle, Triangle(height=1)]`: a Python class and a definition that disagree, and a duplicate.
   This looks like a defect rather than a design question; it follows from question 8 (dropped positions) and pinning it as a strict xfail assumes so.

## Answers

`pytest tests/laws --questions` lists the same tests with their current status.

| # | Theme | Topic | Answer | Affected test |
|---|---|---|---|---|
| 1 | traversal | field on a list | | `test_path_matches_reference` (`last_on_list`) |
| 2 | errors | negative index past the start | | `test_get_does_not_mutate_source` (strict xfail) |
| 3 | errors | slice past the end | | slices are not generated yet |
| 4 | errors | prefix inside a function | | `test_prefix_in_function_does_not_parse` |
| 5 | errors | bare `.` | | `test_bare_prefix_is_empty` |
| 6 | errors | `default=` | | `test_default_ignored_when_parseable`, `test_default_replaces_parse_errors` |
| 7 | repetition | list source without `indices` | | `test_unindexed_outer_takes_first`, `test_unindexed_inner_takes_first` |
| 8 | repetition | dropped positions | | `test_nested_sections_drop_empty`, `test_mapper_pinned[indices-select-empty]` |
| 9 | repetition | nested sections vs joined path | | `test_nested_sections_drop_empty`, `test_mapper_pinned[missing-vs-empty]` |
| 10 | repetition | projection in a source path | | `test_mapper_pinned[source-double-projection]`, `test_mapper_pinned[source-projection-of-lists]` |
| 11 | repetition | `indices=[]` as "all" | | `test_mapper_pinned[indices-order-ignored]`, `test_mapper_pinned[indices-duplicate]` |
| 12 | repetition | negative `indices` | | `test_mapper_pinned[indices-negative]`, `test_mapper_pinned[indices-out-of-range]` |
| 13 | passes | merge across subclasses | | `test_merge_across_subclasses_keeps_first` |
| 14 | subclasses | unresolvable `m_def` | | `test_from_dict_pinned[unknown-m-def-base-field]`, `[unknown-m-def-subclass-field]`, `[m-def-outside-hierarchy]` |
| 15 | subclasses | field of another subclass | | `test_from_dict_pinned[field-of-other-subclass]` |
| 16 | passes | scalar update modes | | `test_scalar_passes_overwrite` |
| 17 | subclasses | falsy-only subsections | | `test_from_dict_pinned[falsy-only-subsection]` |
| 18 | passes | misaligned element reuse | | `test_append_pass_reuses_misaligned_element` (strict xfail) |
