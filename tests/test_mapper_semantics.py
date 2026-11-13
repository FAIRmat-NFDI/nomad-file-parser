import pytest
from nomad.metainfo import MSection, Quantity, SubSection

from nomad_file_parser.mapping_parser import MetainfoParser, Path


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
