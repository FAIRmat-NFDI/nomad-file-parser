#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import io
import mmap
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pint
from nomad.metainfo import Quantity as mQuantity
from nomad.utils import get_logger

from .file_parser import FileParser

_UNSET = object()


# Complete float literals only. np.fromstring('1.2.3', sep=' ') is 1.2 on NumPy 1.x.
_FLOAT_TOKEN = re.compile(r'[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?')


def _is_numeric_dtype(dtype: Any) -> bool:
    if dtype is None:
        return False
    if dtype in (int, float, complex):
        return True
    try:
        return np.issubdtype(dtype, np.number)
    except Exception:
        return False


def _is_integer_dtype(dtype: Any) -> bool:
    if dtype is int:
        return True
    try:
        return np.issubdtype(dtype, np.integer)
    except Exception:
        return False


def _is_int_token(token: str) -> bool:
    if token.startswith(('+', '-')):
        token = token[1:]
    return bool(token) and token.isdecimal()


def _compile_bytes_pattern(pattern: Any) -> re.Pattern:
    if isinstance(pattern, re.Pattern):
        if isinstance(pattern.pattern, bytes):
            return pattern
        return re.compile(pattern.pattern.encode(), pattern.flags)
    return re.compile(pattern.encode())


def _as_int_array_if_integral(data: np.ndarray) -> np.ndarray:
    if np.all(np.mod(data, 1) == 0):
        return data.astype(int)
    return data


@dataclass(frozen=True)
class ParsedPointer:
    """A parsed source range and the quantity that owns it."""

    start: int
    end: int
    quantity_name: str | None = None


class ParsePattern:
    def __init__(self, **kwargs):
        self._head = kwargs.get('head', '')
        self._key = kwargs.get('key', '')
        value = kwargs.get('value', 're_float_array')
        if value.startswith('re_'):
            token = ''
            if 'float' in value:
                token += r'Ee\+\d\.\-'
            if 'int' in value:
                token += r'\d'
            if 'str' in value:
                token += r'\w'
            if 'array' in value:
                token += r' '
            value = rf'[{token}]+'
        self._value = value
        self._tail = kwargs.get('tail', '\n')
        self._re_pattern = None

    @property
    def re_pattern(self):
        if self._re_pattern is None:
            head = rf'{self._head}[\s\S]*?' if self._head else ''
            key = rf'{self._key}\s*\:*\=*\s*' if self._key else ''
            self._re_pattern = rf'{head}{key}\s*\:*\=*\s*({self._value}){self._tail}'
        return self._re_pattern

    def __call__(self, text, repeats=True):
        values = []
        units = []
        if repeats:
            for res in self.re_pattern.finditer(text):
                unit = res.groupdict().get('__unit', None)
                values.append(
                    ''.join(
                        [
                            group.decode()
                            for group in res.groups()
                            if group and group != unit
                        ]
                    )
                )
                units.append(unit.decode() if unit is not None else None)
        else:
            res = self.re_pattern.search(text)
            if res is not None:
                unit = res.groupdict().get('__unit', None)
                units.append(unit.decode() if unit is not None else None)
                values.append(
                    ''.join(
                        [
                            group.decode()
                            for group in res.groups()
                            if group and group != unit
                        ]
                    )
                )


class Quantity:
    """
    Class to define a quantity to be parsed in the TextParser.

    Arguments:
        quantity: string to identify the name or a metainfo quantity to initialize the
            quantity object.
        re_pattern: pattern to be used by re for matching. Ideally, overlaps among
            quantities for a given parser should be avoided.
        sub_parser: instance of TextParser to perform local parsing
            within a matched block
        str_operation: external function to be performed on a matched block
        dtype: data type of the quantity
        unit: unit of the quantity
        shape: shape of the quantity
        repeats: denotes if multiple matches are expected
        convert: switch automatic data type conversion
        comment: character to denote a line to be ignored

    """

    def __init__(
        self,
        quantity: str | mQuantity,
        re_pattern: str | list | ParsePattern,
        **kwargs,
    ):
        self.name: str
        self.dtype: str | Any
        self.unit: str
        self.shape: list[int]
        if isinstance(quantity, str):
            self.name = quantity
            self.dtype = None
            self.unit = None
            self.shape = None
        elif isinstance(quantity, mQuantity):
            self.name = quantity.name
            self.dtype = (
                quantity.type.type
                if isinstance(quantity.type, np.dtype)
                else quantity.type
            )
            self.unit = quantity.unit
            # check if metainfo shape has dependencies
            self.shape = quantity.shape
            if False in [str(i).isdigit() for i in self.shape]:
                self.shape = None
        # override metainfo
        self.dtype = kwargs.get('dtype', self.dtype)
        self.unit = kwargs.get('unit', self.unit)
        self.shape = kwargs.get('shape', self.shape)
        self._re_pattern: str = (
            re_pattern.re_pattern
            if isinstance(re_pattern, ParsePattern)
            else '|'.join(re_pattern)
            if isinstance(re_pattern, list)
            else re_pattern
        )
        if isinstance(re_pattern, str):
            # reformulate regular expression to capture range
            match = re.findall(r'_capture:(.+?)(?:__(?:start|end)|\Z)', re_pattern)
            re_patterns = [m for m in match] if match else [re_pattern]
        elif isinstance(re_pattern, ParsePattern):
            re_patterns = [re_pattern.re_pattern]
        else:
            re_patterns = re_pattern
        self.re_patterns = [_compile_bytes_pattern(p) for p in re_patterns]
        self.multiline = kwargs.get(
            'multiline', isinstance(re_pattern, str) and len(re_patterns) == 1
        )
        self.exact_match = kwargs.get('exact_match', not self.multiline)
        self.units_mapping = kwargs.get('units_mapping', {})
        self.str_operation: Callable = kwargs.get('str_operation', None)
        self.sub_parser: TextParser = kwargs.get('sub_parser', None)
        self.repeats: bool = kwargs.get('repeats', False)
        self.convert: bool = kwargs.get('convert', True)
        self.flatten: bool = kwargs.get('flatten', True)
        self.reduce: bool = kwargs.get('reduce', True)
        self.comment: str = kwargs.get('comment', None)

    @property
    def re_pattern(self):
        """
        Returns a compiled re pattern.
        """
        if isinstance(self._re_pattern, str):
            re_pattern = self._re_pattern.replace('__unit', f'__unit_{self.name}')
            self._re_pattern = re.compile(re_pattern.encode())
        elif isinstance(self._re_pattern, re.Pattern) and isinstance(
            self._re_pattern.pattern, str
        ):
            self._re_pattern = re.compile(
                self._re_pattern.pattern.encode(), self._re_pattern.flags
            )
        return self._re_pattern

    @re_pattern.setter
    def re_pattern(self, val: str):
        self._re_pattern = val

    def to_data(self, val_raw: str):
        """
        Converts the parsed block into data.
        """

        def convert(val):
            if isinstance(val, str):
                if self.dtype is None:
                    if val.isdecimal():
                        return int(val)
                    else:
                        try:
                            return float(val)
                        except Exception:
                            pass
                else:
                    try:
                        return self.dtype(val)
                    except Exception:
                        pass

                return val

            elif isinstance(val, list | np.ndarray):
                try:
                    dtype = float if self.dtype is None else self.dtype
                    val_test = np.array(val, dtype=dtype)
                    if self.dtype is None:
                        val_test = _as_int_array_if_integral(val_test)
                    return val_test

                except Exception:
                    self.dtype = None
                    return [convert(v) for v in val]

            elif isinstance(val, dict):
                return {k: convert(v) for k, v in val.items()}

            else:
                return val

        if isinstance(val_raw, TextParser):
            return val_raw

        if val_raw is None:
            return None

        if not val_raw:
            return None

        if self.comment is not None and isinstance(val_raw, (str, bytes)):
            if val_raw.strip()[0] == self.comment:
                return None

        if (
            self.str_operation is None
            and self.flatten
            and self.convert
            and (self.dtype is None or _is_numeric_dtype(self.dtype))
        ):
            data = self._try_parse_numeric(val_raw)
            if data is not _UNSET:
                return data

        data: Any = val_raw

        if self.str_operation is not None:
            data = self.str_operation(val_raw)

        elif self.flatten:
            data = val_raw.strip().split()
            if self.reduce:
                data = data[0] if len(data) == 1 else data

        if self.convert:
            data = convert(data)

        if isinstance(data, np.ndarray) and self.shape:
            try:
                data = np.reshape(data, self.shape)
            except Exception:
                pass

        return data

    def _try_parse_numeric(self, val_raw: Any):
        """Parse a whitespace-separated numeric block, or return _UNSET to fall back."""
        if not isinstance(val_raw, (str, bytes)):
            return _UNSET
        if isinstance(val_raw, bytes):
            try:
                text = val_raw.strip().decode()
            except UnicodeDecodeError:
                return _UNSET
        else:
            text = val_raw.strip()
        if not text:
            return _UNSET
        tokens = text.split()

        if all(_is_int_token(t) for t in tokens) and (
            self.dtype is None or _is_integer_dtype(self.dtype)
        ):
            values = [int(t) for t in tokens]
            if self.reduce and len(values) == 1:
                value = values[0]
                if self.dtype is None:
                    return value
                try:
                    return self.dtype(value)
                except (OverflowError, ValueError, TypeError):
                    return _UNSET
            try:
                data = np.array(values, dtype=int if self.dtype is None else self.dtype)
            except OverflowError:
                if self.dtype is not None:
                    return _UNSET
                data = np.array(values, dtype=object)
            return self._finish_numeric_array(data)

        if self.dtype is not None and _is_integer_dtype(self.dtype):
            return _UNSET
        if not all(_FLOAT_TOKEN.fullmatch(t) for t in tokens):
            return _UNSET
        try:
            data = np.fromstring(text, sep=' ', dtype=self.dtype or float)
        except (ValueError, TypeError):
            return _UNSET
        if len(data) == 0 or len(data) != len(tokens):
            return _UNSET
        if self.reduce and len(data) == 1:
            return data[0]
        if self.dtype is None:
            data = _as_int_array_if_integral(data)
        return self._finish_numeric_array(data)

    def _finish_numeric_array(self, data: np.ndarray):
        if self.shape:
            try:
                data = np.reshape(data, self.shape)
            except Exception:
                pass
        return data

    def __repr__(self) -> str:
        if not self.sub_parser:
            return self.name
        sub_quantities = [q.name for q in self.sub_parser.quantities]
        return f'{self.name}({", ".join(sub_quantities[:5])}{"..." if len(sub_quantities) > 5 else ""})'


class TextParser(FileParser):
    """
    Parser for unstructured text files using the re module. The quantities to be parsed
    are given as a list of Quantity objects which specifies the regular expression. The mmap
    module is used to handle the file.

    By default ``findall`` is False, so each requested quantity is matched with
    ``re.finditer`` / ``re.search``. This is the lazy path used by ``get(key)`` and
    ``parse(key)``. Set ``findall=True`` to compile all non-sub-parser quantities into
    one combined ``re.findall`` pass when parsing the whole file. Combined findall does
    not tolerate overlapping patterns.

    Performance: ``findall=False`` is cheapest when only a few keys are read; each extra
    ``get()`` scans the file again. ``findall=True`` is usually faster if most quantities
    will be read, but a large union of complex or overlapping regexes can be much slower
    (catastrophic backtracking). ``line_parsing=True`` avoids mapping the whole block and
    is meant for very large files; it is typically slower on moderate files. Leave
    ``record_spans=False`` unless you need visualization — span recording re-runs matches.

    Arguments:
        mainfile: the path to the file to be parsed
        quantities: list of Quantity objects to be parsed.
        logger: optional logger
        findall: if True will employ re.findall, otherwise re.finditer. Default False.
        file_offset: offset in reading the file
        file_length: length of the chunk to be read from the file
        allow_overlap: if True, will match each quantity to the file block
        max_lines: maximum number of lines to cache in a multiline search
        line_parsing: if True will perform line by line matching
        record_spans: if True, record source ranges for visualization while parsing
    """

    def __init__(
        self,
        mainfile: str | None = None,
        quantities: list[Quantity] | None = None,
        logger=None,
        **kwargs,
    ):
        if logger is None:
            logger = get_logger(__name__)
        super().__init__(mainfile, logger=logger, open=kwargs.get('open', None))
        self._quantities: list[Quantity] = quantities
        self.findall: bool = kwargs.get('findall', False)
        self.findlazy: bool = kwargs.get('findlazy', None)
        self._file_length: int = kwargs.get('file_length', 0)
        self._file_offset: int = kwargs.get('file_offset', 0)
        self._file_pad: int = 0
        self._parsed: list[int] = []
        # True if multiple quantities can match a line
        self.allow_overlap = kwargs.get('allow_overlap', False)
        # maximum mumber of lines to cache in a multiline search
        self.max_lines = kwargs.get('max_lines', 10)
        self.line_parsing = kwargs.get('line_parsing', False)
        if quantities is None:
            self.init_quantities()
        # check quantity patterns are valid
        re_has_group = re.compile(r'\(.+\)')
        for i in range(len(self._quantities) - 1, -1, -1):
            if self._quantities[i].sub_parser:
                continue
            try:
                if len(self._quantities[i].re_patterns) == 1:
                    assert (
                        re_has_group.search(
                            self._quantities[i].re_pattern.pattern.decode()
                        )
                        is not None
                    )
            except Exception as e:
                self.logger.error(
                    'Invalid quantity pattern',
                    exc_info=e,
                    data=dict(quantity=self.quantities[i].name),
                )
                self._quantities.pop(i)
        self._re_findall: re.Pattern = None
        self._parsed_pointers: list[ParsedPointer] = []
        self._record_spans: bool = kwargs.get('record_spans', False)

    def copy(self):
        """
        Returns a copy of the object excluding the parsed results.
        """
        return TextParser(
            self.mainfile,
            self.quantities,
            self.logger,
            findall=self.findall,
            findlazy=self.findlazy,
            allow_overlap=self.allow_overlap,
            max_lines=self.max_lines,
            line_parsing=self.line_parsing,
            record_spans=self._record_spans,
        )

    def reset(self):
        """Reset parsed results and the source pointers collected during parsing."""
        super().reset()
        self._parsed_pointers = []

    def init_quantities(self):
        """
        Initializes the quantities list.
        """
        self._quantities = []

    @property
    def quantities(self):
        """
        Returns the list of quantities to be parsed.
        """
        return self._quantities

    @quantities.setter
    def quantities(self, val: list[Quantity]):
        """
        Sets the quantities list.
        """
        self._file_handler = None
        self._results = None
        self._parsed_pointers = []
        self._quantities = val

    @property
    def file_offset(self):
        """
        Integer offset in loading the file taking into account mmap pagination.
        """
        return self._file_offset

    @file_offset.setter
    def file_offset(self, val: int):
        """
        Sets starting point where the file is read.
        """
        self._file_pad = val % mmap.PAGESIZE
        self._file_offset = (val // mmap.PAGESIZE) * mmap.PAGESIZE
        self.reset()

    @property
    def file_length(self):
        """
        Length of the file chunk to be loaded.
        """
        return self._file_length

    @file_length.setter
    def file_length(self, val: int):
        """
        Sets the length of the file to be read.
        """
        self._file_length = val
        self.reset()

    @property
    def file_mmap(self):
        """
        Memory mapped representation of the file.
        """
        if self._file_handler is None:
            with self.open(self.mainfile, 'rb') as f:
                if isinstance(f, io.TextIOWrapper):
                    self._file_handler = mmap.mmap(
                        f.fileno(),
                        self._file_length,
                        access=mmap.ACCESS_COPY,
                        offset=self._file_offset,
                    )
                    # set the extra chunk loaded before the intended offset to empty
                    self._file_handler[: self._file_pad] = b' ' * self._file_pad
                else:
                    self._file_handler = [(0, f.seek(0, 2))]
            self._file_pad = 0
        return self._file_handler

    @property
    def file_pointers(self):
        """
        List of (start, end) indices of blocks in the file to be parsed.
        """
        if self._file_handler is None:
            with self.open(self.mainfile, 'rb') as f:
                self._file_handler = [(0, f.seek(0, 2))]
        return self._file_handler

    def keys(self):
        """
        Returns all the quantity names.
        """
        return [quantity.name for quantity in self.quantities]

    def items(self):
        """
        Returns an iterable name, value of the parsed quantities
        """
        for key in self.keys():
            yield key, self.get(key)

    def visualize(
        self,
        context_lines: int | None = None,
        key: str | None = None,
        leaves_only: bool = True,
    ):
        """Create a source view highlighting parsed quantities.

        Args:
            context_lines: Surrounding lines to include in a compact source view.
                ``None`` (the default) displays the complete file.
            key: Quantity name or dotted quantity path to highlight. If omitted,
                all parsed quantities are shown.
            leaves_only: Show only quantities without nested parsers. This is the
                default; set to ``False`` to include ancestors, made progressively
                more transparent.
        """
        from .visualizer import TextParserVisualizer

        def parse_visualization_children(parser: TextParser):
            """Parse deferred nested parsers so all leaf pointers are available."""
            for value in (parser._results or {}).values():
                parsers = value if isinstance(value, list) else [value]
                for child in parsers:
                    if isinstance(child, TextParser):
                        if child._results is None or not child._parsed_pointers:
                            child._record_spans = True
                            child.parse()
                        parse_visualization_children(child)

        self._record_spans = True
        if self._results is None or not self._parsed_pointers:
            self.reset()
            self._record_spans = True
            self.parse()
        parse_visualization_children(self)
        return TextParserVisualizer(
            self,
            context_lines=context_lines,
            key=key,
            leaves_only=leaves_only,
        )

    def show_visualization(
        self,
        context_lines: int | None = None,
        path: str | Path | None = None,
        key: str | None = None,
        leaves_only: bool = True,
    ) -> Path:
        """Open the text-parser visualization in a browser tab.

        Args:
            context_lines: Surrounding lines to include in a compact source view.
                ``None`` (the default) displays the complete file.
            key: Quantity name or dotted quantity path to highlight. If omitted,
                all parsed quantities are shown.
            leaves_only: Show only quantities without nested parsers. This is the
                default; set to ``False`` to include ancestors, made progressively
                more transparent.
        """
        return self.visualize(
            context_lines=context_lines,
            key=key,
            leaves_only=leaves_only,
        ).show(path)

    def _record_match(self, match, quantity_name: str | None = None):
        """Record leaf capture spans while parsing, for later visualization."""
        spans = [
            match.span(index + 1)
            for index in range(len(match.groups()))
            if match.span(index + 1) != (-1, -1)
        ] or [match.span()]
        absolute_spans = self._absolute_spans(spans)
        self._parsed_pointers.extend(
            ParsedPointer(start, end, quantity_name) for start, end in absolute_spans
        )

    def _absolute_spans(self, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Map spans in the loaded block back to the original main file."""
        if not isinstance(self._file_handler, list):
            return [
                (self._file_offset + start, self._file_offset + end)
                for start, end in spans
            ]

        absolute_spans = []
        loaded_start = 0
        for source_start, source_end in self._file_handler:
            loaded_end = loaded_start + source_end - source_start
            for start, end in spans:
                overlap_start = max(start, loaded_start)
                overlap_end = min(end, loaded_end)
                if overlap_start < overlap_end:
                    absolute_spans.append(
                        (
                            self._file_offset
                            + source_start
                            + overlap_start
                            - loaded_start,
                            self._file_offset
                            + source_start
                            + overlap_end
                            - loaded_start,
                        )
                    )
            loaded_start = loaded_end
        return absolute_spans

    def _add_value(self, quantity: Quantity, value: list[str], units):
        """
        Converts the list of parsed blocks into data and apply the corresponding units.
        """
        try:
            value_processed = [quantity.to_data(val) for val in value]
            for n, _ in enumerate(value_processed):
                unit = units[n] if units[n] else quantity.unit
                if not unit:
                    continue
                if isinstance(unit, str):
                    value_processed[n] = pint.Quantity(value_processed[n], unit)
                else:
                    value_processed[n] = value_processed[n] * unit

            if not quantity.repeats and value_processed:
                value_processed = value_processed[0]

            self._results[quantity.name] = value_processed
        except Exception:
            self.logger.warning(
                'Error setting value', data=dict(quantity=quantity.name)
            )

    def _load_block(self) -> bytes | mmap.mmap:
        """
        Loads the file block to be parsed.
        """
        if not isinstance(self._file_handler, list):
            return self._file_handler

        with self.open(self.mainfile, 'rb') as f:
            block = b''
            for span in self._file_handler:
                f.seek(span[0] + self._file_offset)
                block += f.read(span[1] - span[0])
            return block

    def _parse_quantities(self, quantities: list[Quantity]):
        """
        Parse a list of quantities.
        """

        def record_matches(quantity: Quantity, block):
            matches = (
                quantity.re_pattern.finditer(block)
                if quantity.repeats
                else [quantity.re_pattern.search(block)]
            )
            for match in matches:
                if match is not None:
                    self._record_match(match, quantity.name)

        if len(self._results) == 0 and self._re_findall is not None:
            # attempt at optimization
            re_findall_b = self._re_findall
        else:
            re_findall = '|'.join([q.re_pattern.pattern.decode() for q in quantities])
            if len(quantities) == 1:
                # necessary to add a dummy variable to make multiple matches
                re_findall = f'{re_findall}|(__dummy__)'
            re_findall_b = re.compile(re_findall.encode())
            if self._re_findall is None:
                self._re_findall = re_findall_b

        # map matches to quantities
        block = self._load_block()
        matches = re.findall(re_findall_b, block)
        current_index = 0
        for quantity in quantities:
            values = []
            units = []
            n_groups = quantity.re_pattern.groups

            non_empty_matches = []
            for match in matches:
                if isinstance(match, bytes):
                    match = [match]
                non_empty_match = [
                    m for m in match[current_index : current_index + n_groups] if m
                ]
                if not non_empty_match:
                    continue
                non_empty_matches.append(non_empty_match)
            index_unit = quantity.re_pattern.groupindex.get(
                f'__unit_{quantity.name}', None
            )
            for non_empty_match in non_empty_matches:
                try:
                    if index_unit is not None:
                        unit = non_empty_match.pop(index_unit - 1)
                        units.append(unit.decode())

                    else:
                        units.append(None)

                    values.append(' '.join([m.decode() for m in non_empty_match]))
                except Exception:
                    self.logger.error(
                        'Error parsing quantities.', data=dict(quantity=quantity.name)
                    )

            current_index += n_groups

            if not values:
                continue

            self._add_value(quantity, values, units)
            if self._record_spans:
                record_matches(quantity, block)

    def _parse_quantity(self, quantity: Quantity):
        """
        Parse a single quantity.
        """
        value = []
        units = []
        block = self._load_block()
        re_matches = (
            quantity.re_pattern.finditer(block)
            if quantity.repeats
            else [quantity.re_pattern.search(block)]
        )
        for res in re_matches:
            if res is None:
                continue
            if quantity.sub_parser is not None:
                sub_parser = quantity.sub_parser.copy()
                sub_parser.mainfile = self.mainfile
                sub_parser.logger = self.logger
                sub_parser._record_spans = self._record_spans
                if sub_parser.findlazy is None:
                    sub_parser.findlazy = self.findlazy
                if not res.groups():
                    continue
                if self._record_spans:
                    scope_spans = self._absolute_spans(
                        [(res.span(1)[0], res.span(len(res.groups()))[1])]
                    )
                    self._parsed_pointers.extend(
                        ParsedPointer(start, end, quantity.name)
                        for start, end in scope_spans
                    )
                start = res.span(1)[0]
                sub_parser._file_offset = self._file_offset + start
                sub_parser._file_handler = [
                    (res.span(n + 1)[0] - start, res.span(n + 1)[1] - start)
                    for n in range(len(res.groups()))
                ]
                value.append(sub_parser if sub_parser.findlazy else sub_parser.parse())

            else:
                if self._record_spans:
                    self._record_match(res, quantity.name)
                try:
                    unit = res.groupdict().get(f'__unit_{quantity.name}', None)
                    units.append(unit.decode() if unit is not None else None)
                    value.append(
                        ' '.join(
                            [
                                group.decode()
                                for group in res.groups()
                                if group and group != unit
                            ]
                        )
                    )
                except Exception:
                    self.logger.error('Error parsing quantity.')

        if not value:
            return

        if quantity.sub_parser is not None:
            self._results[quantity.name] = value if quantity.repeats else value[0]

        else:
            self._add_value(quantity, value, units)

    def _parse_line(self, key=None):
        self._blocks = [[[None] * len(q.re_patterns)] for q in self.quantities]
        self._line_pointers = [[[None] * len(q.re_patterns)] for q in self.quantities]
        self._units = [None] * len(self.quantities)
        self._multiline = True in [q.multiline for q in self.quantities]
        self._repeats = True in [q.repeats for q in self.quantities]
        with self.open(self.mainfile, 'rb') as fileobj:
            fileobj.seek(self._file_offset)
            # for multiline support
            lines = []
            parsed = []
            while True:
                position = fileobj.tell()
                line = fileobj.readline()
                if not line:
                    break
                if self._file_length > 0 and position > (
                    self._file_offset + self._file_length
                ):
                    break
                if not self._repeats and False not in [
                    None not in block[-1] for block in self._blocks
                ]:
                    break
                if self._multiline:
                    lines.append(line)
                    lines = lines[-self.max_lines :]
                for n_q, quantity in enumerate(self.quantities):
                    if n_q in parsed:
                        continue
                    blocks = self._blocks[n_q][-1]
                    pointers = self._line_pointers[n_q][-1]
                    n_re = [n for n, p in enumerate(blocks) if p is None]
                    if not n_re:
                        if not quantity.repeats:
                            parsed.append(n_q)
                            continue
                        else:
                            blocks = [None] * len(quantity.re_patterns)
                            self._blocks[n_q].append(blocks)
                            pointers = [None] * len(quantity.re_patterns)
                            self._line_pointers[n_q].append(pointers)
                            n_re = [0]

                    if quantity.multiline:
                        match = re.search(
                            quantity.re_patterns[n_re[0]], b''.join(lines)
                        )
                    # faster matching
                    elif quantity.exact_match:
                        match = re.match(quantity.re_patterns[n_re[0]], line)
                    else:
                        match = re.search(quantity.re_patterns[n_re[0]], line)
                    if match:
                        lines = []
                        if quantity.sub_parser:
                            block = [
                                match.span(n + 1) for n in range(len(match.groups()))
                            ]
                            if not block:
                                # if nothing is captured capture the whole block
                                # shift to current line
                                start = len(match.string) - len(line)
                                block = [
                                    (match.span()[0] - start, match.span()[1] - start)
                                ]
                            block = [(s + position, e + position) for s, e in block]
                            blocks[n_re[0]] = block
                        else:
                            match_start = position - (len(match.string) - len(line))
                            full_span = (
                                match_start + match.span()[0],
                                match_start + match.span()[1],
                            )
                            captured_spans = [
                                (
                                    match_start + match.span(index + 1)[0],
                                    match_start + match.span(index + 1)[1],
                                )
                                for index in range(len(match.groups()))
                                if match.span(index + 1) != (-1, -1)
                            ]
                            pointers[n_re[0]] = (full_span, captured_spans)
                            values = [g or b'' for g in match.groups()]
                            if values:
                                unit_index = quantity.re_patterns[
                                    n_re[0]
                                ].groupindex.get('__unit')
                                if unit_index:
                                    self._units[n_q] = values.pop(
                                        unit_index - 1
                                    ).decode()
                                blocks[n_re[0]] = b' '.join(values).decode()
                            else:
                                # if noting is captured, capture spanned block
                                blocks[n_re[0]] = (
                                    position,
                                    position + match.span()[1] - match.span()[0],
                                )

                        if not self.allow_overlap:
                            break

            for n_q, quantity in enumerate(self.quantities):
                if quantity.sub_parser:
                    data = []
                    for blocks in self._blocks[n_q]:
                        if None in blocks:
                            continue
                        sub_parser = quantity.sub_parser.copy()
                        sub_parser.mainfile = self.mainfile
                        sub_parser.line_parsing = True
                        sub_parser.allow_overlap = self.allow_overlap
                        sub_parser.max_lines = self.max_lines
                        sub_parser._file_offset = blocks[0][0][0]
                        sub_parser._file_length = (
                            blocks[-1][-1][-1] - sub_parser._file_offset
                        )
                        data.append(sub_parser)
                    if data:
                        self._results.setdefault(
                            quantity.name, data if quantity.repeats else data[0]
                        )
                    if self._record_spans:
                        for blocks in self._blocks[n_q]:
                            if None not in blocks:
                                scope_start = blocks[0][0][0]
                                scope_end = blocks[-1][-1][1]
                                self._parsed_pointers.append(
                                    ParsedPointer(scope_start, scope_end, quantity.name)
                                )
                else:
                    blocks = self._blocks.pop(n_q)
                    self._blocks.insert(n_q, None)
                    data = []
                    for block in blocks:
                        if None in block or not block:
                            continue
                        strings = [b for b in block if isinstance(b, str)]
                        if strings:
                            data.append(' '.join(strings))
                        else:
                            spans = [b for b in block if isinstance(b, tuple)]
                            fileobj.seek(spans[0][0])
                            data.append(
                                fileobj.read(spans[-1][-1] - spans[0][0]).decode()
                            )
                    if data:
                        data = [quantity.to_data(d) for d in data]
                        unit = (
                            quantity.units_mapping.get(
                                self._units[n_q], self._units[n_q]
                            )
                            or quantity.unit
                        )
                        if unit:
                            data = [
                                pint.Quantity(d, unit)
                                if isinstance(unit, str)
                                else d * unit
                                for d in data
                            ]
                        self._results[quantity.name] = (
                            data if quantity.repeats else data[0]
                        )

                    if self._record_spans:
                        for pointers in self._line_pointers[n_q]:
                            if None not in pointers:
                                captured_spans = [
                                    pointer
                                    for _, matches in pointers
                                    for pointer in matches
                                ]
                                if captured_spans:
                                    self._parsed_pointers.extend(
                                        ParsedPointer(start, end, quantity.name)
                                        for start, end in captured_spans
                                    )
                                else:
                                    self._parsed_pointers.append(
                                        ParsedPointer(
                                            pointers[0][0][0],
                                            pointers[-1][0][1],
                                            quantity.name,
                                        )
                                    )

    def parse(self, key=None):
        """
        Triggers parsing of quantity with name key, if key is None will parse all quantities.

        Returns file parser.
        """
        if self._results is None:
            self._results = dict()

        if self.line_parsing:
            self._parse_line()
            return self

        if self.file_mmap is None:
            return self

        if self.findall:
            if len(self._results) > 1:
                return self

            n_results = 0
            while True:
                # use find all to parse quantities with no sub_parser.
                quantities_findall = [
                    q
                    for q in self.quantities
                    if q.name not in self._results and q.sub_parser is None
                ]
                if not quantities_findall:
                    break

                # recursively parse quantities
                self._parse_quantities(quantities_findall)

                if n_results == len(self._results):
                    # will stop if no more matches are found
                    break
                n_results = len(self._results)

            for quantity in self._quantities:
                if quantity.sub_parser is not None:
                    self._parse_quantity(quantity)

        else:
            for quantity in self._quantities:
                if quantity.name == key or key is None:
                    if quantity.name not in self._results:
                        self._parse_quantity(quantity)

        # free up memory
        if self.findall:
            if isinstance(self._file_handler, mmap.mmap):
                self._file_handler.close()

        return self

    def clear(self):
        """
        Deletes the file mapping for all sub parsers.
        """
        for quantity in self.quantities:
            if quantity.sub_parser is not None:
                quantity.sub_parser.clear()
        self._file_handler = None


class DataTextParser(TextParser):
    """
    Parser for structured data text files using numpy.loadtxt

    Arguments:
        mainfile: the file to be parsed
        dtype: data type
    """

    def __init__(self, **kwargs):
        self._dtype: type = kwargs.get('dtype', float)
        self._mainfile_contents: str = kwargs.get('mainfile_contents', '')
        super().__init__(**kwargs)

    def parse(self, key=None):
        super().parse(key=key)
        if key == 'data' or not self._results:
            try:
                data = None
                if self.mainfile is not None:
                    data = np.loadtxt(
                        self.mainfile,
                        **{
                            key: val
                            for key, val in self._kwargs.items()
                            if key in np.loadtxt.__code__.co_varnames
                        },
                    )
                else:
                    if not self._mainfile_contents and self.mainfile_obj:
                        with self.open_mainfile_obj() as mainfile_obj:
                            self._mainfile_contents = mainfile_obj.read()
                    if self._mainfile_contents:
                        buffer = self._mainfile_contents
                        if isinstance(buffer, str):
                            buffer = buffer.encode()
                        if buffer:
                            data = np.frombuffer(buffer, dtype=self._dtype)
                if data is not None:
                    self._results['data'] = data
            except Exception:
                self.logger.error('Failed to load data file.')
