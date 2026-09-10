# API reference

This page gives a high-level overview of the public API of `nomad-file-parser`.
It is distilled from the in-code docstrings; consult those for the full detail.

## Public exports

The top-level package (`nomad_file_parser`) exposes the parsers most users need:

| Import | Purpose |
|--------|---------|
| `TextParser` (alias `UnstructuredTextFileParser`) | Declarative parsing of unstructured text via regular-expression `Quantity` definitions. |
| `DataTextParser` | Text parsing plus `numpy.loadtxt`-based loading of structured numeric data. |
| `Quantity`, `ParsePattern` | Building blocks for describing what a `TextParser` extracts. |
| `XMLParser` | XPath-style access to XML files. |
| `TarParser` | Access to the members of a TAR archive. |
| `MappingParser` | Declarative, annotation-driven mapping between tree-like representations (see below). |
| `FileParser`, `ArchiveWriter` (alias `Parser`) | Base classes for building custom file parsers and archive writers. |

For usage-oriented walkthroughs, see the [text-parser](../howto/text-parser.md) and
[mapping-parser](../howto/mapping-parser.md) how-to guides.

## The mapping-parser framework

`MappingParser` is an annotation-driven system for parsing several file formats
(XML, HDF5, JSON, text) and transforming data between representations. Data access
is expressed with `jmespath` (or `jsonpath_ng`) path expressions, and the mapping
itself is declared through metainfo annotations or plain dictionaries rather than
imperative code.

### Key components

- `MappingParser` — abstract base class for a format-specific parser.
- `XMLParser`, `HDF5Parser`, `MetainfoParser`, `TextParser` — the format-specific
  implementations.
- `Mapper` / `Transformer` — the declarative mapping and transformation
  specifications. `Mapper` composes sub-mappers for nested structures; `Transformer`
  runs a named function over source paths.

### Conversion pipeline

A conversion from a source file to a target `data_object` proceeds in stages:
the source file is loaded into a format-specific object, serialized to a dictionary,
traversed by the mapper to extract and transform values along their paths, merged into
the target's data, and finally deserialized into the target's native object (for
example, a populated metainfo `MSection`). The `convert` method drives this end to end:

```python
with HDF5Parser(filepath='data.h5') as source:
    with MetainfoParser(data_object=MySection()) as target:
        source.convert(target)
```

## API stability

The docstrings mark which parts of the framework are safe to depend on.

**Stable — the parser-developer interface:**
`MappingParser` and its format-specific subclasses (`XMLParser`, `HDF5Parser`,
`MetainfoParser`, `TextParser`), the `MappingParser.convert` and `MappingParser.parse`
entry points, the `Mapper`/`Transformer` specifications used *declaratively* (in
annotations or dict specs), and the `BaseMapper.from_dict` factory. Use, extend, and
rely on these.

**Internal — implementation details that may change without notice:**
the path-resolution and jmespath internals (`PathParser`, `JmespathParser`,
`TreeInterpreter`, `ParsedResult`, `JmespathOptions`), the `Path`/`Data` structures,
`BaseMapper` itself (use `BaseMapper.from_dict` instead), and the metainfo-specific
mapper internals. Do not instantiate, subclass, or rely on these directly.
