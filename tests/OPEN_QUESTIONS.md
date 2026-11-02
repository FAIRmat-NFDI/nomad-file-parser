# Open questions on path semantics

Behaviours found while writing `tests/test_path_laws.py` where it is not clear whether they are intended.
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

## Answers

| # | Topic | Answer | Affected test |
|---|---|---|---|
| 1 | field on a list | | `test_interpreter_matches_path` (`last_on_list`) |
| 2 | negative index past the start | | `test_get_does_not_mutate_source` |
| 3 | slice past the end | | slices are not generated yet |
| 4 | prefix inside a function | | `test_prefix_in_function_does_not_parse` |
| 5 | bare `.` | | `test_bare_prefix_is_empty` |
| 6 | `default=` | | `test_default_ignored_when_parseable`, `test_default_replaces_parse_errors` |
| 7 | list source without `indices` | | `test_unindexed_outer_takes_first`, `test_unindexed_inner_takes_first` |
| 8 | dropped positions | | `test_nested_sections_drop_empty`, `test_mapper_pinned[indices-select-empty]` |
| 9 | nested sections vs joined path | | `test_nested_sections_follow_joined_path`, `test_mapper_pinned[missing-vs-empty]` |
| 10 | projection in a source path | | `test_mapper_pinned[source-double-projection]`, `test_mapper_pinned[source-projection-of-lists]` |
| 11 | `indices=[]` as "all" | | `test_mapper_pinned[indices-order-ignored]`, `test_mapper_pinned[indices-duplicate]` |
| 12 | negative `indices` | | `test_mapper_pinned[indices-negative]`, `test_mapper_pinned[indices-out-of-range]` |
