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
    from .text_parser import TextParser


DEFAULT_PARSED_BLOCK_COLORS = (
    '#fff59d',
    '#b2dfdb',
    '#bbdefb',
    '#e1bee7',
    '#ffccbc',
    '#c8e6c9',
)


@dataclass(frozen=True)
class ParsedBlock:
    """An absolute, half-open byte range in a parser's main file."""

    start: int
    end: int
    quantity_name: str | None = None
    depth: int | None = None


class TextParserVisualizer:
    """Render quantities parsed by a :class:`TextParser`.

    The visualizer is deliberately HTML based: a returned instance renders directly
    in Jupyter notebooks and :meth:`to_html` can be embedded in a web view.  It does
    not require IPython or any frontend dependency.
    """

    def __init__(
        self,
        parser: TextParser,
        context_lines: int | None = None,
        key: str | None = None,
        leaves_only: bool = True,
    ):
        """Initialize a source view.

        By default, only quantities without nested parsers are displayed. Set
        ``leaves_only=False`` to display all parsed quantities; parent quantities
        are progressively more transparent than their descendants.
        Set ``context_lines`` to a non-negative integer to show only the
        highlighted lines and that many surrounding lines. The default,
        ``None``, displays the complete file.
        """
        if context_lines is not None and context_lines < 0:
            raise ValueError('context_lines must be greater than or equal to zero')
        self.parser = parser
        self.context_lines = context_lines
        self.key = key
        self.leaves_only = leaves_only
        self.source = self._read_source()
        self.blocks = self._blocks()

    def _read_source(self) -> bytes:
        if self.parser.mainfile is None:
            raise ValueError('A mainfile is required to visualize parsed blocks')
        with self.parser.open(self.parser.mainfile, 'rb') as file:
            return file.read()

    def _blocks(self) -> list[ParsedBlock]:
        """Return parser-local spans as absolute byte ranges.

        When ``leaves_only`` is set, container spans are omitted and only leaf
        quantity spans are returned.
        """

        def matches_key(quantity_name: str | None) -> bool:
            """Return whether a displayed quantity matches ``key``."""
            if quantity_name is None or self.key is None:
                return False
            _, _, relative_name = quantity_name.partition('.')
            candidates = {
                quantity_name,
                relative_name,
                quantity_name.rsplit('.', 1)[-1],
            }
            return self.key in candidates

        self._container_quantities: set[str] = set()
        blocks = self._parsed_blocks()

        # Clamp potentially stale offsets and remove empty ranges before rendering.
        blocks = [
            ParsedBlock(
                max(0, block.start),
                min(len(self.source), block.end),
                block.quantity_name,
                block.depth,
            )
            for block in blocks
            if block.start < len(self.source)
            and block.end > 0
            and block.start < block.end
        ]
        if self.key is not None:
            blocks = [block for block in blocks if matches_key(block.quantity_name)]
        if self.leaves_only:
            blocks = [
                block
                for block in blocks
                if block.quantity_name not in self._container_quantities
            ]
        return [
            ParsedBlock(
                block.start,
                block.end,
                block.quantity_name,
                block.depth,
            )
            for block in sorted(blocks, key=lambda item: (item.start, item.end))
        ]

    def _parsed_blocks(self) -> list[ParsedBlock]:
        """Resolve pointer ownership from the parsed parser tree."""

        def children(parser):
            for name, value in (parser._results or {}).items():
                if hasattr(value, '_parsed_pointers'):
                    yield name, value
                elif isinstance(value, list):
                    yield from (
                        (f'{name}[{index}]', item)
                        for index, item in enumerate(value)
                        if hasattr(item, '_parsed_pointers')
                    )

        def collect(parser, quantity_prefix=None, depth=0):
            child_parsers = list(children(parser))
            child_names = {
                child_label.split('[', 1)[0] for child_label, _ in child_parsers
            }
            self._container_quantities.update(
                f'{quantity_prefix}.{child_name}' if quantity_prefix else child_name
                for child_name in child_names
            )
            blocks = [
                ParsedBlock(
                    pointer.start,
                    pointer.end,
                    quantity_name=(
                        f'{quantity_prefix}.{pointer.quantity_name}'
                        if quantity_prefix and pointer.quantity_name
                        else pointer.quantity_name or quantity_prefix
                    ),
                    depth=depth,
                )
                for pointer in parser._parsed_pointers
            ]
            for child_label, child in child_parsers:
                # Repeated sub-parsers share one logical parent quantity. Keep
                # the repeat index in the display label, but not in the parent
                # path so child blocks can identify their enclosing scope.
                child_name = child_label.split('[', 1)[0]
                child_id = (
                    f'{quantity_prefix}.{child_name}' if quantity_prefix else child_name
                )
                blocks.extend(collect(child, child_id, depth + 1))
            return blocks

        parser_label = type(self.parser).__name__
        return collect(self.parser, quantity_prefix=parser_label)

    def _visible_range(self) -> tuple[int, int]:
        if not self.blocks:
            return (0, 0)
        assert self.context_lines is not None
        leaf_blocks = [
            block
            for block in self.blocks
            if block.quantity_name not in self._container_quantities
        ]
        blocks = leaf_blocks or self.blocks
        starts = [block.start for block in blocks]
        ends = [block.end for block in blocks]
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

        def transparent_color(color: str, opacity: float) -> str:
            """Return a translucent CSS color while preserving the block hue."""
            if len(color) == 7 and color.startswith('#'):
                red, green, blue = (
                    int(color[index : index + 2], 16) for index in (1, 3, 5)
                )
                return f'rgba({red}, {green}, {blue}, {opacity})'
            return color

        def opacity_for_depth(depth: int, max_depth: int) -> float:
            """Return a depth-based opacity, keeping the deepest level opaque."""
            minimum_opacity = 0.35
            return minimum_opacity + (1 - minimum_opacity) * depth / max_depth

        start, end = (
            (0, len(self.source))
            if self.context_lines is None
            else self._visible_range()
        )
        blocks = sorted(self.blocks, key=lambda block: (block.start, block.end))
        positions = {start, end}
        for block in blocks:
            positions.add(max(start, block.start))
            positions.add(min(end, block.end))
        positions = sorted(positions)

        rendered = []
        color_by_quantity = {}
        max_depth = max(
            (block.depth for block in blocks if block.depth is not None), default=0
        )
        for block in blocks:
            quantity = block.quantity_name or f'{block.start}:{block.end}'
            color_by_quantity.setdefault(
                quantity,
                DEFAULT_PARSED_BLOCK_COLORS[
                    len(color_by_quantity) % len(DEFAULT_PARSED_BLOCK_COLORS)
                ],
            )
        for left, right in zip(positions, positions[1:]):
            text = escape(self.source[left:right].decode('utf-8', errors='replace'))
            matching_blocks = [
                block for block in blocks if block.start <= left and right <= block.end
            ]
            highlighted = max(
                matching_blocks,
                key=lambda block: block.depth if block.depth is not None else -1,
                default=None,
            )
            if highlighted:
                background_color = color_by_quantity[
                    highlighted.quantity_name
                    or f'{highlighted.start}:{highlighted.end}'
                ]
                if (
                    highlighted.depth is not None
                    and highlighted.quantity_name in self._container_quantities
                ):
                    background_color = transparent_color(
                        background_color,
                        opacity_for_depth(highlighted.depth, max_depth),
                    )
                label = (
                    f' title="{escape(highlighted.quantity_name.rsplit(".", 1)[-1], quote=True)}"'
                    if highlighted.quantity_name
                    else ''
                )
                rendered.append(
                    f'<mark data-byte-start="{left}" data-byte-end="{right}" '
                    f'style="background-color:{background_color};"{label}>{text}</mark>'
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
