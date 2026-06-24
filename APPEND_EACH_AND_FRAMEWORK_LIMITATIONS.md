# Mapping Parser: append_each Mode and Framework Limitations

**Commit**: 75266dd52fe090bfe91f9ee1480bc9a7e98400b2
**Date**: 2026-06-24

## Summary

Added `update_mode='append_each'` to fix list-handling bug where transformer functions returning lists were treated as single items instead of being iterated. This commit also includes comprehensive testing that revealed architectural limitations in section-level transformer support.

## Problem Solved: List Handling

### Before
```python
# update_mode='append' with function returning list
def get_criteria(self, source):
    return [{'a': 1}, {'b': 2}]  # Returns list

# Result: Entire list treated as single item
target = [[{'a': 1}, {'b': 2}]]  # Nested list (wrong!)
```

### After
```python
# update_mode='append_each' iterates over items
def get_criteria(self, source):
    return [{'a': 1}, {'b': 2}]

# Result: Each item appended individually
target = [{'a': 1}, {'b': 2}]  # Flat list (correct!)
```

## Implementation

**File**: `src/nomad_file_parser/mapping_parser.py`

Added `append_each` mode that:
1. Checks if incoming data is a list
2. Iterates over list items
3. Appends each item individually
4. Falls back to regular append for non-lists
5. Ensures updated data is written back to target

## Testing

Added comprehensive test coverage (1,846 lines across 7 test files):

### Test Files
1. `tests/test_append_each_mode.py` (242 lines) - Core append_each functionality
2. `tests/test_append_each_assumptions.py` (435 lines) - Hypothesis property tests
3. `tests/test_update_mode_append_behavior.py` (356 lines) - Append mode comparison
4. `tests/test_framework_assumptions.py` (253 lines) - Framework architectural tests
5. `tests/test_polymorphic_mapper_bug.py` (382 lines) - Polymorphic section behavior
6. `tests/test_polymorphic_mapper_bug_simple.py` (151 lines) - Simplified polymorphism tests

### Key Findings from Tests

**✓ append_each works correctly** (6/6 tests pass)
- Handles lists, non-lists, empty targets
- Preserves order
- Integrates with existing update modes

**✗ Section-level transformers unsupported** (architectural limitation)
- Transformer functions cannot be used on `Section.m_def` annotations
- Only direct paths work: `'@.path[*]'` ✓, `('func', ['@.path'])` ✗
- Root cause: `build_section_mapper()` line 2621 assigns to `mapper['source']` instead of `mapper['mapper']`

**✗ Annotations don't inherit** (architectural limitation)
- Annotations on base classes don't appear on subclasses
- Parser-specific schemas must repeat base class annotations
- See `test_annotation_inheritance()` for demonstration

## Limitations NOT Fixed

This commit does NOT enable section-level transformers. Workarounds required:

### 1. Field-level transformer pattern (recommended)
Use direct path on section annotation, transformers on field annotations:

```python
# Section annotation (direct path)
add_mapping_annotation(
    SelfConsistency.m_def,
    OUT_KEY,
    '@.scf_convergence[*]'  # Direct path, no transformer
)

# Field annotations (with transformers)
add_mapping_annotation(
    SelfConsistency.type,
    OUT_KEY,
    ('derive_type', ['.criterion_name'])  # Field transformer works!
)
```

### 2. Manual instance creation in normalize()
Call transformer manually and create instances programmatically:

```python
def normalize(self, archive, logger):
    self.out_parser.convert(archive_handler, remove=False)

    if archive.data.method:
        criteria = self.out_parser.get_all_criteria(self.out_parser.data)
        for criterion_dict in criteria:
            archive.data.method.numerical_settings.append(
                SelfConsistency(**criterion_dict)
            )
```

### 3. Pre-structure data
Ensure source data matches schema structure, use direct path with `update_mode='append_each'`:

```python
add_mapping_annotation(
    SelfConsistency.m_def,
    OUT_KEY,
    '@.scf_convergence[*]',
    update_mode='append_each'
)
```

## Related Documentation

For detailed analysis of the section-level transformer limitation, see:
- **Obsidian note**: `mapping-parser-section-level-transformers-unsupported.md`
- Root cause code location: `mapping_parser.py:2617-2622`
- Why it doesn't work: Section annotations assigned to `mapper['source']` instead of `mapper['mapper']`

## Backward Compatibility

✓ Fully backward compatible:
- Existing `update_mode='append'` unchanged
- New `append_each` mode is opt-in
- No breaking changes to existing parsers

## Usage

```python
from nomad.datamodel.metainfo.annotations import Mapper

# Add annotation with append_each mode
add_mapping_annotation(
    Section.field,
    'parser_key',
    ('transformer_func', ['@.source.path']),
    update_mode='append_each'  # Use new mode
)
```

## See Also

- Test files: `tests/test_framework_assumptions.py`, `tests/test_polymorphic_mapper_bug.py`
- Example usage: FHI-aims SCF convergence criteria implementation
- Framework architecture: `mapping_parser.py` lines 2617-2680
