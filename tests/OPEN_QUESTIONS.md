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

   On `{'c': [...]}` with the six calculations below, the joined path agrees in JMESPath and `Path`, and the mapper (`C` → `S` → `E`, both `indices=[]`) drops more:

   | Calculation | `s[*].e` in JMESPath | `s[*].e` in `Path` | in `c[*].s[*].e` | in the mapper |
   |---|---|---|---|---|
   | `{'s': [{'e': 1}, {'e': 2}]}` | `[1, 2]` | `[1, 2]` | kept | `{S: [{E: 1}, {E: 2}]}` |
   | `{'s': []}` | `[]` | `[]` | kept as `[]` | dropped |
   | `{}` (no `s`) | `None` | `None` | dropped | dropped |
   | `{'s': [{'x': 0}]}` | `[]` | `[]` | kept as `[]` | dropped |
   | `{'s': None}` | `None` | `None` | dropped | dropped |
   | `{'s': [{'e': 3}]}` | `[3]` | `[3]` | kept | `{S: [{E: 3}]}` |
   | **result** | | | `[[1, 2], [], [], [3]]` | `[[1, 2], [3]]` |

   A projection drops an element only when the rest of the expression gives `None` (`s` missing or not a list), as the JMESPath specification prescribes; neither the path nor the mapper keeps all six positions.

   **Closed:** the joined path is standard JMESPath, and `Path` agrees with it (`test_joined_path_is_jmespath`), so it is a valid reference for the shape of nested sections. What remains is the mapper's additional dropping of `[]`, which is question 8.
10. **One mapper over two list levels does not nest.**
   Sections nest when each list level has its own repeating mapper: `C` (source `c`) with the child `S` (source `.s`) gives one `C` per calculation, each holding one `S` per step.
   They do not nest when a single repeating mapper's source already crosses both levels (`c[*].s` or `c[*].s[*]`, whose value is a list of lists): the mapper makes one section per outer element and reads its child `.e` from the inner list as a whole, keeping that list's first element.
   On `{'c': [{'s': [{'e': 1}, {'e': 2}]}, {'s': [{'e': 3}]}]}`:

   | Mapper | Source value | Sections | Comparable path | in `Path` | in JMESPath |
   |---|---|---|---|---|---|
   | `C` (`c`) → `S` (`.s`) → `E` (`.e`) | per level | `C: [{S: [{E: 1}, {E: 2}]}, {S: [{E: 3}]}]`, nested | `c[*].s[*].e` | `[[1, 2], [3]]` | `[[1, 2], [3]]` |
   | `S` (`c[*].s[*]`) → `E` (`.e`) | `[[{e: 1}, {e: 2}], [{e: 3}]]` | `S: [{E: 1}, {E: 3}]`, one per calculation, first step only | `c[*].s[0].e`, the explicit first step | `[1, 3]` | `[1, 3]` |
   | `S` (`c[*].s`) → `E` (`.e`) | the same | `S: [{E: 1}, {E: 3}]` | `c[*].s.e`, a field on the inner list | `[2, 3]`, the last step (question 1) | `[]`, a field on a list is `null` |
   | `S` (`c[*].s[]`) → `E` (`.e`) | `[{e: 1}, {e: 2}, {e: 3}]`, flattened | `S: [{E: 1}, {E: 2}, {E: 3}]`, one per step | `c[*].s[].e` | `[1, 2, 3]` | `[1, 2, 3]` |

   Flattening with `[]` already gives one section per step, so nothing is missing for that case.
   The mapper's cut to the first inner element is what JMESPath spells explicitly as `[0]`; read implicitly, as a field on the inner list, `Path` takes the last element and JMESPath gives nothing.
   The open points are the two middle rows: should a source whose value is a list of lists be rejected or warned about rather than cut silently to the first inner element, and if it is kept, should the mapper take the first element while a field on a list in `Path` takes the last?
11. **`indices=[]` means "all elements, as a list".**
   `indices` is a field of `Mapper` (`mapping_parser.py`, `indices: list[int] | str | None`) and of the mapping annotation (`nomad.datamodel.metainfo.annotations.Mapper.indices`), where a string names a function or attribute of the parser that yields the list.
   It selects elements of a list source by position, and its value also decides the shape of the result:

   | `indices` | Elements kept | Result | Set by | In JMESPath |
   |---|---|---|---|---|
   | `None` | the first non-empty one (question 7) | one section | `MetainfoParser.build_section_mapper` for a non-repeating subsection | `c[0]` or `c[*] \| [0]`: the element at position 0, empty or not |
   | `[]` | all | a list of sections | `build_section_mapper` for every repeating subsection, and for subclass mappers | `c[*]` |
   | `[0, 2]` | those at source positions 0 and 2 (question 8) | a list | an annotation, explicitly | `[c[0], c[2]]` (multi-select) |
   | `'name'` | `getattr(parser, 'name')`, called if callable | a list | an annotation, explicitly | no equivalent: computed by the parser |

   JMESPath expresses the shape by syntax, `[*]` for a list and `[i]` for one value, so it never needs one value for both roles.
   Its multi-select also behaves differently from an explicit `indices` list: `[c[1], c[0]]` keeps the order given, `[c[0], c[0]]` keeps both, `c[-1]` counts from the end, and `c[5]` gives `None`.

   The two roles come from two tests in `Mapper.get_data`: `if indices and n not in indices` filters, so an empty list filters nothing, and `mapper.indices is None` decides whether the result is a single value or a list.
   The parsers never write `indices=[]` themselves; it follows from `SubSection(repeats=True)`.
   For an explicit list, order is ignored (`[1, 0]` gives source order) and duplicates collapse (`[0, 0]` gives one element).
   Should "all elements" have its own spelling, so that `[]` is not both "no filter" and "make it a list", and should the order of an explicit `indices` list matter?
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
| 1 | steps | field on a list | | `test_field_on_list_reads_last`, `test_pinned_steps[field-on-list]`, `[field-after-closed-projection]`, `[field-on-list-in-filter-condition]` |
| 2 | errors, steps | negative index past the start | | `test_get_does_not_mutate_source`, `test_index_past_start_is_none` (both strict xfail) |
| 3 | errors | slice past the end | | slices are not generated yet |
| 4 | errors | prefix inside a function | | `test_prefix_in_function_does_not_parse` |
| 5 | errors | bare `.` | | `test_bare_prefix_is_empty` |
| 6 | errors | `default=` | | `test_default_ignored_when_parseable`, `test_default_replaces_parse_errors` |
| 7 | repetition | list source without `indices` | | `test_unindexed_outer_takes_first`, `test_unindexed_inner_takes_first` |
| 8 | repetition | dropped positions | | `test_nested_sections_drop_empty`, `test_mapper_pinned[indices-select-empty]` |
| 9 | repetition | nested sections vs joined path | closed: the joined path is JMESPath's; the rest is question 8 | `test_joined_path_is_jmespath`, `test_nested_sections_drop_empty`, `test_mapper_pinned[missing-vs-empty]` |
| 10 | repetition | projection in a source path | | `test_mapper_pinned[source-double-projection]`, `test_mapper_pinned[source-projection-of-lists]` |
| 11 | repetition | `indices=[]` as "all" | | `test_mapper_pinned[indices-order-ignored]`, `test_mapper_pinned[indices-duplicate]` |
| 12 | repetition | negative `indices` | | `test_mapper_pinned[indices-negative]`, `test_mapper_pinned[indices-out-of-range]` |
| 13 | passes | merge across subclasses | | `test_merge_across_subclasses_keeps_first` |
| 14 | subclasses | unresolvable `m_def` | | `test_from_dict_pinned[unknown-m-def-base-field]`, `[unknown-m-def-subclass-field]`, `[m-def-outside-hierarchy]` |
| 15 | subclasses | field of another subclass | | `test_from_dict_pinned[field-of-other-subclass]` |
| 16 | passes | scalar update modes | | `test_scalar_passes_overwrite` |
| 17 | subclasses | falsy-only subsections | | `test_from_dict_pinned[falsy-only-subsection]` |
| 18 | passes | misaligned element reuse | | `test_append_pass_reuses_misaligned_element` (strict xfail) |
