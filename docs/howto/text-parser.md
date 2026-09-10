# Parse text files

ASCII text files are amongst the most common files used. Here, we show you how to parse the text by matching specific [regular expressions](https://realpython.com/regex-python/){:target="_blank" rel="noopener"} in these files. For the following example, consider a file with the following contents:

```text
2020/05/15
               *** super_code v2 ***

system 1
--------
sites: H(1.23, 0, 0), H(-1.23, 0, 0), O(0, 0.33, 0)
latice: (0, 0, 0), (1, 0, 0), (1, 1, 0)
energy: 1.29372

*** This was done with magic source                                ***
***                                x°42                            ***


system 2
--------
sites: H(1.23, 0, 0), H(-1.23, 0, 0), O(0, 0.33, 0)
cell: (0, 0, 0), (1, 0, 0), (1, 1, 0)
energy: 1.29372
```

At the top there is some general information such as date, name of the code (`super_code`)
and its version (`v2`). Then is information for two systems (`system 1` and `system 2`),
separated with a string containing a code-specific value `magic source`. Both system sections contain the quantities `sites` and `energy`, but each have a unique quantity as well, `latice` and `cell`, respectively.

In order to convert the information from this file into the NOMAD archive, we first have to
parse the necessary quantities. The `nomad-file-parser` package provides a `TextParser`
for declarative (i.e., semi-automated) parsing of text files:

```python
from nomad_file_parser import TextParser, Quantity
```

You can define text file parsers as follows:

```python
def str_to_sites(string):
    sym, pos = string.split('(')
    pos = np.array(pos.split(')')[0].split(',')[:3], dtype=float)
    return sym, pos


calculation_parser = TextParser(
    quantities=[
        Quantity(
            'sites',
            r'([A-Z]\([\d\.\, \-]+\))',
            str_operation=str_to_sites,
            repeats=True,
        ),
        Quantity(
            Model.lattice,
            r'(?:latice|cell): \((\d)\, (\d), (\d)\)\,?\s*\((\d)\, (\d), (\d)\)\,?\s*\((\d)\, (\d), (\d)\)\,?\s*',
            repeats=False,
        ),
        Quantity('energy', r'energy: (\d\.\d+)'),
        Quantity(
            'magic_source',
            r'done with magic source\s*\*{3}\s*\*{3}\s*[^\d]*(\d+)',
            repeats=False,
        ),
    ]
)

mainfile_parser = TextParser(
    quantities=[
        Quantity('date', r'(\d\d\d\d\/\d\d\/\d\d)', repeats=False),
        Quantity('program_version', r'super\_code\s*v(\d+)\s*', repeats=False),
        Quantity(
            'calculation',
            r'\s*system \d+([\s\S]+?energy: [\d\.]+)([\s\S]+\*\*\*)*',
            sub_parser=calculation_parser,
            repeats=True,
        ),
    ]
)
```

The quantities to be parsed can be specified as a list of `Quantity` objects in `TextParser`.
Each quantity should have a name and a *regular expression (re)* pattern to match the value.
The matched value should be enclosed in a group(s) denoted by `(...)`. In addition, we can
specify the following arguments:

- `findall (default=True)`: Switches simultaneous matching of all quantities using `re.findall`.
In this case, overlap between matches is not tolerated, i.e. two quantities cannot share the same
block in the file. If this cannot be avoided, set `findall=False` switching to`re.finditer`.
This will perform matching one quantity at a time which is slower but with the benefit that
matching is done independently of other quantities.
- `repeats (default=False)`: Switches finding multiple matches for a quantity. By default,
only the first match is returned.
- `str_operation (default=None)`: An external function to be applied on the matched value
to perform more specific string operations. In the above example, we defined `str_to_sites` to
convert the parsed value of the atomic sites.
- `sub_parser (default=None)`: A nested parser to be applied on the matched block. This can
also be a `TextParser` object with a list of quantities to be parsed or [other `FileParser` objects](#other-fileparser-classes).
- `dtype (default=None)`: The data type of the parsed value.
- `shape (default=None)`: The shape of the parsed data.
- `unit (default=None)`: The pint unit of the parsed data.
- `flatten (default=True)`: Switches splitting the parsed string into a flat list.
- `convert (default=True)`: Switches automatic conversion of parsed value.
- `comment (default=None)`: String preceding a line to ignore.

A `metainfo.Quantity` object can also be passed as first argument in place of name in order
to define the data type, shape, and unit for the quantity. `TextParser` returns a dictionary
of key-value pairs, where the key is defined by the name of the quantities and the value is
based on the matched re pattern.

To parse a file, specify the path to such file and call the `parse()` function of `TextParser`:

```python
mainfile_parser.mainfile = mainfile
mainfile_parser.parse()
```

This will populate the `mainfile_parser` object with parsed data and it can be accessed
like a Python dict with quantity names as keys or directly as attributes:

```python
mainfile_parser.get('date')
'2020/05/15'

mainfile_parser.calculation
[TextParser(example.out) --> 4 parsed quantities (sites, lattice_vectors, energy, magic_source), TextParser(example.out) --> 3 parsed quantities (sites, lattice_vectors, energy)]
```

## Other FileParser classes

Aside from `TextParser`, other `FileParser` classes are also defined. These include:

- `DataTextParser`: in addition to matching strings as in `TextParser`, this parser uses the `numpy.loadtxt` function to load structured data files. The loaded `numpy.array` data can then be accessed from the property data.

- `XMLParser`: uses the ElementTree module to parse an XML file. The `parse` method of
the parser takes in an XPath-style key to access individual quantities. By default,
automatic data type conversion is performed, which can be switched off by setting
`convert=False`.

- `TarParser`: reads a TAR archive, exposing its members for downstream parsing.

For tree-structured formats and format-to-format conversion, see the declarative
[mapping-annotation framework](mapping-parser.md).
