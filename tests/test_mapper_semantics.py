import copy

import pytest
from laws.shapes import Circle, Drawing, Square, from_dict_shapes, qualified, summary
from nomad.metainfo import MSection, Quantity, SubSection

from nomad_file_parser.mapping_parser import Mapper, MetainfoParser, Path


@pytest.mark.parametrize(
    'fields, expected',
    [
        ({'radius': 1.0}, []),
        ({'radius': 1.0, 'side': 2.0}, [('Square', {'side': 2.0})]),
    ],
)
def test_from_dict_drops_fields_outside_resolved_type(fields, expected, caplog):
    """tests/laws/test_subclasses.py::test_element_keeps_only_fields_of_its_type"""
    assert from_dict_shapes([{'m_def': qualified(Square), **fields}]) == expected
    assert [record.getMessage() for record in caplog.records] == [
        f"Unknown key 'radius' for resolved type {qualified(Square)!r}; skipping"
    ]


def test_from_dict_warns_once_per_key_and_type(caplog):
    parser = MetainfoParser(data_object=Drawing())
    for _ in range(2):
        parser.from_dict(
            {
                'shapes': [
                    {'m_def': qualified(Square), 'radius': 1.0, 'height': 3.0, 'side': 2.0},
                    {'m_def': qualified(Square), 'radius': 1.0, 'side': 2.0},
                    {'m_def': qualified(Circle), 'height': 3.0, 'radius': 1.0},
                ]
            }
        )

    assert [record.getMessage() for record in caplog.records] == [
        f'Unknown key {key!r} for resolved type {qualified(kind)!r}; skipping'
        for key, kind in [('radius', Square), ('height', Square), ('height', Circle)]
    ]
    assert summary(parser.data_object.shapes) == [
        ('Square', {'side': 2.0}),
        ('Square', {'side': 2.0}),
        ('Circle', {'radius': 1.0}),
    ]


class TestPathWithFunction:
    """tests/laws/test_errors.py::test_relative_path_in_function
    tests/laws/test_errors.py::test_relative_path_in_function_under_parent"""
    @pytest.mark.parametrize(
        'query, parent, source, expected_paths, expected_value',
        [
            ('.a.b', None, {'a': {'b': [1, 2]}}, ('a.b', 'a.b'), [1, 2]),
            ('.b', 'a', {'a': {'b': [1, 2]}}, ('a.b', 'b'), [1, 2]),
            (
                'length(.a.b)',
                None,
                {'a': {'b': [1, 2]}},
                ('length(a.b)', 'length(a.b)'),
                2,
            ),
            ('length(.b)', 'a', {'a': {'b': [1, 2]}}, ('length(a.b)', 'length(b)'), 2),
            ('not_null(.n)', None, {'n': None}, ('not_null(n)', 'not_null(n)'), None),
            (
                '.a.b | length(@)',
                None,
                {'a': {'b': [1, 2]}},
                ('a.b | length(@)', 'a.b | length(@)'),
                2,
            ),
            (
                '.b | length(@)',
                'a',
                {'a': {'b': [1, 2]}},
                ('a.b | length(@)', 'b | length(@)'),
                2,
            ),
            (
                'not_null(p.a, p.b)',
                None,
                {'p': {'a': None, 'b': 2}},
                ('not_null(p.a, p.b)', 'not_null(p.a, p.b)'),
                2,
            ),
            (
                'not_null(p.b, p.a)',
                None,
                {'p': {'a': None, 'b': 2}},
                ('not_null(p.b, p.a)', 'not_null(p.b, p.a)'),
                2,
            ),
            (
                'not_null(.a, .b)',
                'p',
                {'p': {'a': None, 'b': 2}},
                ('not_null(p.a, p.b)', 'not_null(a, b)'),
                2,
            ),
            (
                'not_null(.b, .a)',
                'p',
                {'p': {'a': None, 'b': 2}},
                ('not_null(p.b, p.a)', 'not_null(b, a)'),
                2,
            ),
            (
                "length(join(', .', .names))",
                'p',
                {'p': {'names': ['Fe', 'O']}},
                ("length(join(', .', p.names))", "length(join(', .', names))"),
                6,
            ),
            (
                'not_null(.missing, `[1, 2]`)',
                'p',
                {'p': {}},
                ('not_null(p.missing, `[1, 2]`)', 'not_null(missing, `[1, 2]`)'),
                [1, 2],
            ),
            (
                'length([a, b])',
                'p',
                {'p': {'a': 1, 'b': 2}},
                ('length(p.[a, b])', 'length([a, b])'),
                2,
            ),
            (
                'length(.items[?contains(name, `","`)])',
                'p',
                {'p': {'items': [{'name': 'a,b'}, {'name': 'c'}]}},
                (
                    'length(p.items[?contains(name, `","`)])',
                    'length(items[?contains(name, `","`)])',
                ),
                1,
            ),
            (
                'length(."a, .b")',
                'p',
                {'p': {'a, .b': [1, 2]}},
                ('length(p."a, .b")', 'length("a, .b")'),
                2,
            ),
            (
                'length(.a | .b)',
                'p',
                {'p': {'a': {'b': [1, 2]}}},
                ('length(p.a | b)', 'length(a | b)'),
                2,
            ),
            (
                'sort_by(.items, &.score)',
                'p',
                {'p': {'items': [{'score': 2}, {'score': 1}]}},
                ('sort_by(p.items, &score)', 'sort_by(items, &score)'),
                [{'score': 1}, {'score': 2}],
            ),
        ],
    )
    def test_function_relative_argument(
        self, query, parent, source, expected_paths, expected_value
    ):
        absolute_path, relative_path = expected_paths
        path = Path(path=query, parent=Path(path=parent) if parent else None)
        assert path.absolute_path == absolute_path
        assert path.relative_path == relative_path
        section_data = path.parent.get_data(source) if path.parent is not None else source
        assert path.get_data(section_data) == expected_value
        assert path.parser.get_data(path.absolute_path, source) == expected_value


class Inner(MSection):
    value = Quantity(type=float)
    name = Quantity(type=str)


class Root(MSection):
    title = Quantity(type=str)
    count = Quantity(type=int)
    single = SubSection(sub_section=Inner)
    many = SubSection(sub_section=Inner, repeats=True)


class TestFalsyValues:
    """tests/laws/test_subclasses.py::test_falsy_values_are_data"""

    def _test_from_dict(self, data, expected):
        parser = MetainfoParser(data_object=Root())
        parser.from_dict(data)
        assert parser.to_dict() == expected

    @pytest.mark.parametrize(
        'data',
        [
            {'title': '', 'count': 0},
            {'single': {'value': 0.0}},
            {'single': {'value': 0.0, 'name': 'p'}},
            {'many': [{'value': 0.0}, {'value': 1.0}]},
        ],
    )
    def test_from_dict_kept(self, data):
        self._test_from_dict(data, data)

    @pytest.mark.parametrize(
        'data, expected',
        [
            ({'single': {'value': None}}, {}),
            ({'many': []}, {}),
        ],
    )
    def test_from_dict_dropped(self, data, expected):
        self._test_from_dict(data, expected)


class TestSliceBoundaries:
    """tests/laws/test_steps.py::test_slice_step, tests/laws/test_steps.py::test_pinned_slices"""
    @pytest.fixture
    def content(self):
        return {'v': list(range(10))}
    @pytest.mark.parametrize(
        'query, expected',
        [
        ('v[::3]', [0, 3, 6, 9]),
        ('v[0:13:3]', [0, 3, 6, 9]),
        ('v[8:11]', [8, 9]),
        ('v[-11:3]', [0, 1, 2]),
        ('v[-10:2]', [0, 1]),
        ('v[-3:3]', []),
        ],
    )
    def test_slice_boundaries_search(self, content, query, expected):
        assert Path(path=query).get_data(content) == expected

    @pytest.fixture
    def content_settable(self):
        return {'v': list(range(4))}
    @pytest.fixture
    def to_set(self):
        return [10, 20]
    @pytest.mark.parametrize(
        'path, expected',
        [
        ('v[::2]', [10, 1, 20, 3]),
        ('v[::-2]', [0, 20, 2, 10]),
        ('v[4:6]', [0, 1, 2, 3, 10, 20]),
        ('v[5:3:-1]', [0, 1, 2, 3, 20, 10]),
        ],
    )
    def test_slice_boundaries_set(self, content_settable, to_set, path, expected):
        Path(path=path).set_data(to_set, content_settable)
        assert content_settable['v'] == expected


class TestVisitIndex:
    """tests/laws/test_steps.py::test_index_past_start_is_none"""
    @pytest.mark.parametrize(
        'path, source, expected_value',
        [
            ('a[-3]', {'a': [1, 2]}, None),
            ('a[-1]', {'a': []}, None),
            ('a[-2]', {'a': [1, 2]}, 1),
        ],
    )
    def test_negative(self, path, source, expected_value):
        expected_source = copy.deepcopy(source)
        assert Path(path=path).get_data(source) == expected_value
        assert source == expected_source


class TestMapperRepeatsControlsOutput:
    @pytest.mark.parametrize('repeats', [False, True])
    @pytest.mark.parametrize('items', [[{'value': 1}], [{'value': 1}, {'value': 2}]])
    def test_mapper_repeats_controls_list_output(self, repeats, items):
        spec = {
            'source': 'items',
            'target': 'result',
            'mapper': [{'path': '.value', 'target': 'value'}],
            'repeats': repeats,
        }
        mapper = Mapper.from_dict({'mapper': [spec]})
        source = {'items': items}
        assert mapper.get_data(source, MetainfoParser(data=source)) == {
            'result': items if repeats else items[0]
        }
