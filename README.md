# nomad-file-parser
A collection of utilities for parsing files.

## TextParser
Parse unstructured text files using regular expressions.

### Inspecting parsed blocks

`TextParser` exposes `visualize()`. For nested text parsers it uses the stored
byte offsets to highlight only parsed leaf quantities. The returned object
renders directly in Jupyter notebooks, or can be embedded with `to_html()`.

```python
block_parser = parser.get('block')
block_parser.visualize(context_lines=2)
```

To open the view in a browser tab, call:

```python
block_parser.show_visualization(context_lines=2)
```

By default, the generated HTML is stored in a `.nomad-visualizations` directory
next to the parsed file, so it is accessible to the browser. Pass `path=` to
save it elsewhere. For a root `TextParser`, pass `key=` to select the quantity
whose captured values should be highlighted:

```python
parser.show_visualization(key='total_energy')
```

The full source file is shown by default. For a compact view around the marked
block, pass `full_file=False` and choose the number of surrounding lines with
`context_lines`.

## MappingParser
Enables the mapping of contents between python objects that support 
a dictionary-like structure.

## Main contributors
| Name | E-mail     |
|------|------------|
| Alvin Noe Ladines | [ladinesa@physik.hu-berlin.de](mailto:ladinesa@physik.hu-berlin.de)
