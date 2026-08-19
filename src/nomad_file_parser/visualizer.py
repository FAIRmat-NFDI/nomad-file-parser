"""Source views for inspecting the byte ranges consumed by text parsers."""

from __future__ import annotations

import webbrowser
from bisect import bisect_right
from dataclasses import dataclass
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .file_parser import FileParser


@dataclass(frozen=True)
class ParsedBlock:
    """An absolute, half-open byte range in a parser's main file."""

    start: int
    end: int
    color: str | None = None


class TextParserVisualizer:
    """Render leaf quantities parsed by a :class:`TextParser`.

    The visualizer is deliberately HTML based: a returned instance renders directly
    in Jupyter notebooks and :meth:`to_html` can be embedded in a web view.  It does
    not require IPython or any frontend dependency.
    """

    def __init__(
        self,
        parser: FileParser,
        context_lines: int = 3,
        key: str | None = None,
        full_file: bool = True,
    ):
        if context_lines < 0:
            raise ValueError('context_lines must be greater than or equal to zero')
        self.parser = parser
        self.context_lines = context_lines
        self.key = key
        self.full_file = full_file
        self.source = self._read_source()
        self.blocks = self._blocks()

    def _read_source(self) -> bytes:
        if self.parser.mainfile is None:
            raise ValueError('A mainfile is required to visualize parsed blocks')
        with self.parser.open(self.parser.mainfile, 'rb') as file:
            return file.read()

    def _blocks(self) -> list[ParsedBlock]:
        """Return parser-local spans as absolute byte ranges.

        ``TextParser`` stores nested parser selections in ``_file_handler`` as
        ranges relative to ``_file_offset``. Other parser implementations normally
        consume the complete input, which is represented by one full-file range.
        """
        handler = getattr(self.parser, '_file_handler', None)
        offset = getattr(self.parser, '_file_offset', 0) or 0
        length = getattr(self.parser, '_file_length', 0) or 0
        if hasattr(self.parser, '_parsed_pointers'):
            blocks = self._parsed_blocks()
        elif isinstance(handler, list) and all(
            isinstance(span, tuple) and len(span) == 2 for span in handler
        ):
            blocks = [
                ParsedBlock(offset + start, offset + end) for start, end in handler
            ]
        elif length > 0:
            blocks = [ParsedBlock(offset, offset + length)]
        else:
            blocks = [ParsedBlock(0, len(self.source))]

        # Clamp potentially stale offsets and remove empty ranges before rendering.
        return [
            ParsedBlock(
                max(0, block.start), min(len(self.source), block.end), block.color
            )
            for block in blocks
            if block.start < len(self.source)
            and block.end > 0
            and block.start < block.end
        ]

    def _parsed_blocks(self) -> list[ParsedBlock]:
        """Resolve pointer ownership and colors from the parsed parser tree."""
        colors = ['#fff59d', '#b2dfdb', '#bbdefb', '#e1bee7', '#ffccbc', '#c8e6c9']
        color_index = 0

        def children(parser):
            for value in (parser._results or {}).values():
                if hasattr(value, '_parsed_pointers'):
                    yield value
                elif isinstance(value, list):
                    yield from (
                        item for item in value if hasattr(item, '_parsed_pointers')
                    )

        def collect(parser, color=None):
            nonlocal color_index
            blocks = [
                ParsedBlock(start, end, color) for start, end in parser._parsed_pointers
            ]
            for child in children(parser):
                child_color = colors[color_index % len(colors)]
                color_index += 1
                blocks.extend(collect(child, child_color))
            return blocks

        return collect(self.parser)

    def _visible_range(self) -> tuple[int, int]:
        if not self.blocks:
            return (0, 0)
        starts = [block.start for block in self.blocks]
        ends = [block.end for block in self.blocks]
        line_starts = [0]
        line_starts.extend(
            index + 1 for index, byte in enumerate(self.source) if byte == 10
        )

        first_line = max(0, bisect_right(line_starts, min(starts)) - 1)
        last_line = bisect_right(line_starts, max(ends) - 1) - 1
        first_line = max(0, first_line - self.context_lines)
        last_line = min(len(line_starts) - 1, last_line + self.context_lines)
        start = line_starts[first_line]
        end = (
            line_starts[last_line + 1]
            if last_line + 1 < len(line_starts)
            else len(self.source)
        )
        return (start, end)

    def to_html(self) -> str:
        """Return a self-contained HTML source view with parsed ranges marked."""
        start, end = (0, len(self.source)) if self.full_file else self._visible_range()
        blocks = sorted(self.blocks, key=lambda block: (block.start, block.end))
        positions = {start, end}
        for block in blocks:
            positions.add(max(start, block.start))
            positions.add(min(end, block.end))
        positions = sorted(positions)

        rendered = []
        for left, right in zip(positions, positions[1:]):
            text = escape(self.source[left:right].decode('utf-8', errors='replace'))
            highlighted = next(
                (
                    block
                    for block in blocks
                    if block.start <= left and right <= block.end
                ),
                None,
            )
            if highlighted:
                color = (
                    f' style="background-color:{highlighted.color};"'
                    if highlighted.color
                    else ''
                )
                rendered.append(
                    f'<mark data-byte-start="{left}" data-byte-end="{right}"{color}>{text}</mark>'
                )
            else:
                rendered.append(text)

        return (
            '<pre style="margin:0;overflow:auto;white-space:pre;" '
            'aria-label="Parsed file block">' + ''.join(rendered) + '</pre>'
        )

    def _repr_html_(self) -> str:
        return self.to_html()

    def show(self, path: str | Path | None = None) -> Path:
        """Write the view to an HTML file and open it in a new browser tab.

        Args:
            path: Optional destination for the HTML file. If omitted, a temporary
                file is created next to the source file so a desktop browser can
                access it as well.

        Returns:
            The absolute path of the generated HTML file.
        """
        if path is None:
            source_path = Path(self.parser.mainfile)
            output_directory = source_path.parent / '.nomad-visualizations'
            output_directory.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode='w',
                suffix='.html',
                prefix=f'{source_path.stem}-parsed-block-',
                dir=output_directory,
                delete=False,
            ) as file:
                destination = Path(file.name)
                file.write(self.to_html())
        else:
            destination = Path(path).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(self.to_html(), encoding='utf-8')

        if not destination.is_file():
            raise FileNotFoundError(f'Could not create visualization at {destination}')
        webbrowser.open_new_tab(destination.as_uri())
        return destination
