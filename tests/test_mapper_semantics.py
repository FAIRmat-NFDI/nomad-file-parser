import pytest
from nomad.metainfo import MSection, Quantity, SubSection
from nomad_file_parser.mapping_parser import MetainfoParser


class Inner(MSection):
    value = Quantity(type=float)
    name = Quantity(type=str)


class Root(MSection):
    title = Quantity(type=str)
    count = Quantity(type=int)
    single = SubSection(sub_section=Inner)
    many = SubSection(sub_section=Inner, repeats=True)


class TestMetainfoParser:
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
