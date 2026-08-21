# nomad-file-parser

`nomad-file-parser` provides reusable building blocks for extracting data from
files and transferring it into NOMAD data structures. It is designed
for parser authors who need a lightweight, composable way to work with plain
text, XML, HDF5, and TAR files.

## What is included

| Component | Use it for |
| --- | --- |
| `TextParser` and `Quantity` | Extracting values from unstructured text with regular expressions, including nested blocks. |
| `XMLParser` | Reading XML values with a small XPath-style interface. |
| `TarParser` | Accessing files inside a TAR archive by name. |
| `MappingParser` | Converting XML, HDF5, or text data into dictionaries or NOMAD metainfo through declarative mappings. |
| `FileParser` | The common lazy-parsing interface shared by the file parsers. |

The package supports Python 3.10–3.12 and is licensed under Apache-2.0.

## Installation

For normal use, install the package from its published distribution:

```bash
python -m pip install nomad-file-parser
```

For development from a clone, create an environment and install the package
with its development dependencies:

```bash
cd packages/nomad-file-parser
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

[`uv`](https://docs.astral.sh/uv/) can be used instead of `pip` if it is part
of your workflow.

## Quick start: parse a text file

Define the values to capture with `Quantity`, then retrieve them from a
`TextParser`. Values are parsed lazily: reading `parser.get('energy')` triggers
the work only when it is needed.

```python
from nomad_file_parser import Quantity, TextParser

parser = TextParser(
    mainfile='calculation.out',
    quantities=[
        Quantity('program', r'Program:\s*(\w+)', repeats=False),
        Quantity(
            'total_energy',
            r'Total energy:\s*([-+\d.]+)',
            dtype=float,
            repeats=False,
        ),
    ],
)

print(parser.get('program'))       # e.g. 'ExampleCode'
print(parser.total_energy)         # e.g. -12.34
```

Each regular expression must contain a capture group for the value. By default,
whitespace-separated captures are converted to numbers where possible. Use
`dtype`, `shape`, `unit`, `str_operation`, or `convert=False` on a `Quantity`
when the default conversion is not appropriate. Set `repeats=True` for values
that occur more than once.

### Parse line by line

For files that should be processed incrementally, enable line parsing on the
`TextParser`:

```python
parser = TextParser(
    mainfile='calculation.out',
    line_parsing=True,
    max_lines=20,
    quantities=[
        Quantity('energy', r'Energy:\s*([-+\d.]+)', dtype=float),
    ],
)
```

With `line_parsing=True`, the parser reads and matches the file one line at a
time instead of loading the complete search block. A quantity with
`multiline=True` can still match across the most recent lines; `max_lines`
controls how many lines are retained for that matching. Set `multiline=False`
when a quantity must match only the current line. Nested sub-parsers created
from line-parsed blocks inherit line parsing automatically.

In line-parsing mode, pass a list of regular expressions when a quantity is
defined by an ordered sequence of lines. The patterns are matched in order (and
not treated as alternatives), which is useful for delimiting blocks:

```python
Quantity(
    'section',
    [r'BEGIN SECTION', r'END SECTION'],
    sub_parser=TextParser(quantities=[...]),
)
```

For a single-line quantity, use one string pattern instead. Outside line
parsing, a pattern list is combined as an alternation by the parser.

### Parse repeated blocks with a nested parser

Attach a `TextParser` as `sub_parser` to turn each matching block into another
parser. This is useful for repeated calculation, atom, or iteration sections.

```python
from nomad_file_parser import Quantity, TextParser

calculation = TextParser(
    quantities=[
        Quantity('energy', r'Energy\s*=\s*([-+\d.]+)', dtype=float),
    ]
)

parser = TextParser(
    mainfile='calculation.out',
    quantities=[
        Quantity(
            'calculations',
            r'BEGIN CALCULATION\n([\s\S]+?)END CALCULATION',
            repeats=True,
            sub_parser=calculation,
        )
    ],
)

energies = [block.energy for block in parser.calculations]
```

## Inspect text-parser matches

`TextParser.visualize()` returns an HTML-capable view that highlights parsed
values and nested parser scopes. It renders in Jupyter notebooks and can be
saved with `to_html()`.

```python
block = parser.calculations[0]
view = block.visualize(key='energy', context_lines=2)
html = view.to_html()
```

For a browser view, use `show_visualization()`:

```python
block.show_visualization(key='energy', context_lines=2)
```

The HTML is stored in `.nomad-visualizations` beside the parsed file unless a
different `path` is supplied. `context_lines=None` (the default) displays the
full source; pass a non-negative number to show only the highlighted area with
that many surrounding lines. `key` accepts a quantity name or dotted quantity
path and shows only its parsed spans. For nested parsers, call `visualize()` on
the nested block. Leaf quantities are shown by default; pass
`leaves_only=False` to also show enclosing scopes.

## Other file formats

All `FileParser` implementations offer lazy access through `get()` and
attribute access. Compressed `.gz`, `.bz2`, and `.xz` files are opened
automatically by `FileParser`.

```python
from nomad_file_parser import TarParser, XMLParser

xml = XMLParser('results.xml')
version = xml.get('metadata/version')

archive = TarParser('results.tar')
member = archive.get('output.log')  # a file-like object, or None if absent
```

Use the parser as a context manager when it holds an open file resource:

```python
from nomad_file_parser import TarParser

with TarParser('results.tar') as archive:
    output = archive.get('output.log')
    if output is not None:
        text = output.read().decode()
```

## Mapping structured data to NOMAD

`MappingParser` supplies adapters for HDF5, XML, text, and NOMAD metainfo.
It represents input as nested dictionaries and uses a mapper to copy or
transform source paths into a target. XML and HDF5 attributes use an `@` prefix;
the value of an element that also has attributes is stored under `__value`.

For an archive conversion, configure mapping annotations on the target
metainfo, select the annotation key, and call `convert`:

```python
from nomad_file_parser.mapping_parser import HDF5Parser, MetainfoParser

with HDF5Parser(filepath='results.h5') as source:
    with MetainfoParser(data_object=my_section, annotation_key='hdf5') as target:
        source.convert(target)
```

The package tests contain complete examples of XML, HDF5, and text mappings in
[`tests/test_mapping_parser.py`](tests/test_mapping_parser.py). The mapping
interfaces are intended for NOMAD parser and schema developers; for simple file
extraction, prefer `TextParser`, `XMLParser`, or `TarParser` directly.

## Development

Run the test suite from this package directory:

```bash
python -m pytest tests
```

Lint and verify formatting with Ruff:

```bash
ruff check .
ruff format . --check
```

## Contributing

Please include focused tests for parser changes. Test fixtures and representative
sample files live under `tests/`; avoid adding unnecessarily large production
outputs. Issues and contributions are welcome in the
[project repository](https://github.com/FAIRmat-NFDI/nomad-file-parser).

## Maintainer

Alvin Noe Ladines — [ladinesa@physik.hu-berlin.de](mailto:ladinesa@physik.hu-berlin.de)
