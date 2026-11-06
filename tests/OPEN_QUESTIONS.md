# Open questions on path semantics

Behaviours found while writing the law tests in `tests/laws/` where it is not clear whether they are intended.
Each answer decides the matching test: a strict xfail asserts the agreed behaviour and fails until the code does it; a pinned test (marked `question(n)`, without xfail) records today's behaviour while the question is open.
Questions 1 to 18 were reviewed with Alvin Ladines on 2026-11-06; the **Answer** lines record the outcome.
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

   **Answer:** a read returns `None` and leaves the source untouched. The set-mode result is not settled.
3. **Slice past the end of a list.**
   `a[0:5]` and `a[-5:]` on a two-element list give `None`; JMESPath clamps the bounds and returns both elements (`visit_slice` returns `None` in search mode once a bound exceeds the length).
   A start of exactly `-len` fails too: `v[-10:2]` on ten elements gives `None`. On a five-element list, `Path` differs from JMESPath (which agrees with Python) in 120 of 486 combinations of start, stop and step; a read never changes the list.

   **Answer:** a slice selects as JMESPath and Python do: bounds beyond the ends are clamped, and `[::3]` takes every third element up to the end.
4. **Relative prefix inside a function call.**
   The `Mapper` annotation docstring's example `length(.array.set.set)` gives `None`: the leading `.` is stripped only at the start of the path or after whitespace, so it stays inside the call, the expression does not parse, and the error is swallowed.
   Should relative paths work inside functions, or should the docstring change?
   Under a parent `a`, `not_null(.b)` becomes the absolute path `a.not_null(.b)`: the parent is prepended outside the call.

   **Answer:** they should work. `.p` inside a call is read like `.p` on its own, under the parent where there is one, and its value, `None` included, is passed to the function.
5. **Bare `.`** gives `None` (it becomes the empty expression).
   Should it mean the same as `.@`, or is it invalid?
   The current node is written `@` or `.@`; both give the object passed (`test_at_is_current`, `test_prefix_is_dropped`).
6. **`default=`** is returned only when the expression fails to parse, not when the path is missing: `a.x` on `{'a': {}}` gives `None` even with `default='S'`.

   **Open, two positions:** a default should replace any failure, a missing path included, since the caller asked for a fallback; or the case where an inner segment (`a`) is missing should be told apart from a missing last segment (`x`), which a single default cannot express. How to write a default for one segment only is not settled.

## Mapper tree (`Mapper.get_data`)

7. **List source without `indices`.**
   A mapper whose source resolves to a list keeps only the first non-empty element when `indices` is not set: source `a` with child `.x` on `{'a': [{'x': 1}, {'x': 2}]}` gives `{'A': {'X': 1}}`.
   Is that how a non-repeating section is meant to read a repeated source?

   **Answer:** yes, the first element is mapped and the others are dropped. Conversely, a repeating subsection fed a single object reads it as a list of one (`test_repeating_section_reads_a_dict_as_one_element`, already the case).
8. **Dropped positions.**
   With `indices` set, elements whose children are all empty are dropped and the later ones move up: nested sources `a` → `.y` → `.z` on `[{'y': {'z': 3}}, {'x': 2}, {'y': {'z': 4}}]` give `[{'Y': {'Z': 3}}, {'Y': {'Z': 4}}]`, without a record that element 1 was skipped.
   Should repeating subsections keep their positions, e.g. to stay aligned with a sibling quantity read by index?

   **Answer:** the current order is accepted: `indices` select by source position first, then empty elements are dropped, without a record.

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

   **Open, two positions:** the nesting depth should follow the schema, not the shape of the data, so that a schema can cast a source into the shape it needs without a reshaping function; and, from the other side, a single object under a repeating subsection should be read as a list (question 7). To be investigated further.
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

   **Answer:** ignoring the order and the repeats of an explicit list is not wanted: `indices` should select like a JMESPath multi-select, in the order given and with repeats. Either way the behaviour is to be documented and tested.
12. **Negative entries in `indices` match nothing.**
   `indices=[-1]` gives `{}`, since the source positions `n` compared against it are never negative, whereas the path step `[-1]` selects the last element.
   An out-of-range entry (`[5]`) also gives `{}` silently.
   Should negative entries count from the end, as in paths, or be rejected?

   **Answer:** negative entries count from the end, as the path step `[k]` does.

## Polymorphic subsections (`MetainfoParser`)

Questions 13 to 18 were run on `test/pbt-path-laws` at `99ccf35`, on an unannotated base `Shape` with the subclasses `Circle` (`radius`), `Square` (`side`) and `Triangle` (`height`) under the repeating subsection `Drawing.shapes`.

13. **Merging across subclasses keeps the first type.**
   Two passes with `update_mode='merge'`, `Circle` under `k1` and then `Square` under `k2`, on `{radius: 1, side: 2}` give `[Circle(radius=1)]`: the second pass aligns `Square` with the existing element at position 0, the first type wins and `side` is lost without a warning.
   Should a merge at a position whose `m_def` differs append instead, fail, or keep this behaviour?
   A second finding: with `Circle` and `Square` under `k1` and `Triangle` under `k2`, merging gives `[Circle(radius=1), Square()]`. The second pass maps one element, yet the `Square` at position 1 loses its `side` (`test_merge_leaves_unaddressed_sections`, strict xfail: a merge should change only the positions it addresses).
14. **An unresolvable `m_def` falls back to the base.**
   In `from_dict`, an element whose `m_def` names no section of the hierarchy (unknown, or a section outside it) is built as the declared base type.
   With a base field (`name`) it survives as a `Shape`; with a subclass field it is dropped as empty. Neither case is logged.
   Should an unresolvable `m_def` be reported, or rejected?

   **Answer:** it should raise. Low priority: inside NOMAD the metainfo parser writes the `m_def` itself, so it can only happen when a class that is not a NOMAD section is annotated.
15. **A field of another subclass is dropped silently.**
   `{m_def: Square, radius: 1}` gives no element: `radius` is not a `Square` quantity, `m_set` fails inside a bare `except`, and the element is dropped as empty.
   Should a value that does not fit the resolved type be reported?

   **Open:** it should not fail silently; whether it raises or warns is to be decided.
16. **Scalar update modes all overwrite.**
   A second pass replaces a scalar (`Drawing.title`) under `append`, `merge` and `replace` alike, whereas the `Path.set_data` docstring describes `append` as "keep existing data if present" and the dictionary-level code keeps the current scalar under `merge`.
   Which is intended at the archive level, and should the docstring change?
17. **Falsy-only subsections are dropped.**
   A subsection whose only value is falsy (`Circle(radius=0.0)`, `Shape(name='')`) is treated as empty by `from_dict` (`or v` in the emptiness check) and removed, while the `Mapper` keeps falsy values (`is_not_value` compares with `None`, `[]`, `{}`).
   Is this intended, or should the emptiness check match the mapper's?

   **Answer:** a defect. Falsy values are data; the emptiness check should match the mapper's.
18. **A later pass reuses a misaligned element and reassigns its `m_def`.**
   Pass `k1` maps `Circle` and `Triangle`, pass `k2` maps nothing, both with `append`, on `{height: 1}`.
   Pass 1 drops the empty `Circle` from the archive but keeps `{m_def: Circle}` at position 0 of the parser's intermediate data, where the archive now holds the `Triangle`.
   Pass 2 replays the data by position, reuses that `Triangle` instance and sets its `m_def` to `Circle` (`sub_section.m_def = section_def`), so the result is `[Triangle with m_def Circle, Triangle(height=1)]`: a Python class and a definition that disagree, and a duplicate.
   This looks like a defect rather than a design question; it follows from question 8 (dropped positions) and pinning it as a strict xfail assumes so.
19. **Sibling subsections of the same base type share every annotated subclass** (FAIRmat-NFDI/nomad-file-parser#19).
   Subclass selection scans the base type's subclasses for an annotation under the key, with no notion of the destination subsection, so every annotated subclass lands in every sibling subsection, and fields read under one key are split across them by the subclass hierarchy.

   **Answer:** a defect. The subsection a subclass is routed to decides where it goes (`test_subclass_routed_to_its_subsection`, strict xfail, routing through the subsection's `mapper_m_def`).

## Answers

`pytest tests/laws --questions` lists the same tests with their current status.

| # | Theme | Topic | Answer | Affected test |
|---|---|---|---|---|
| 1 | steps | field on a list | | `test_field_on_list_reads_last`, `test_pinned_steps[field-on-list]`, `[field-after-closed-projection]`, `[field-on-list-in-filter-condition]` |
| 2 | errors, steps | negative index past the start | `None`, source untouched | `test_get_does_not_mutate_source`, `test_index_past_start_is_none` (strict xfail) |
| 3 | steps | slices | clamped, as in JMESPath | `test_slice_step`, `test_pinned_slices` (strict xfail where bounds reach the ends) |
| 4 | errors | relative path inside a function | evaluated, value passed on | `test_relative_path_in_function`, `test_relative_path_in_function_under_parent` (strict xfail) |
| 5 | errors | bare `.` | | `test_bare_prefix_is_empty`, `test_at_is_current` |
| 6 | errors | `default=` | open, two positions | `test_default_replaces_only_parse_errors` |
| 7 | repetition | list source without `indices` | first element, intended | `test_unindexed_outer_takes_first`, `test_unindexed_inner_takes_first`, `test_repeating_section_reads_a_dict_as_one_element` |
| 8 | repetition | dropped positions | accepted | `test_nested_sections_follow_joined_path`, `test_indices_are_source_positions` |
| 9 | repetition | nested sections vs joined path | closed: the joined path is JMESPath's; the rest is question 8 | `test_joined_path_is_jmespath`, `test_nested_sections_follow_joined_path` |
| 10 | repetition | one mapper over two list levels | open, two positions | `test_single_mapper_over_two_levels_takes_first` |
| 11 | repetition | `indices` order and repeats | as a JMESPath multi-select | `test_indices_keep_order_and_repeats` (strict xfail) |
| 12 | repetition | negative `indices` | count from the end | `test_negative_indices_count_from_the_end` (strict xfail) |
| 13 | passes | merge across subclasses | | `test_merge_across_subclasses_keeps_first`, `test_merge_leaves_unaddressed_sections` (strict xfail) |
| 14 | subclasses | unresolvable `m_def` | raise, low priority | `test_unresolvable_m_def_raises` (strict xfail) |
| 15 | subclasses | field of another subclass | open: raise or warn | `test_element_keeps_only_fields_of_its_type` |
| 16 | passes | scalar update modes | | `test_scalar_passes_overwrite` |
| 17 | subclasses | falsy-only subsections | defect: falsy values are data | `test_falsy_values_are_data` (strict xfail) |
| 18 | passes | misaligned element reuse | | `test_append_pass_reuses_misaligned_element` (strict xfail) |
| 19 | subclasses | sibling subsections | defect: route by subsection | `test_subclass_routed_to_its_subsection` (strict xfail) |
