"""Section types: which subclass the parser creates, and how `from_dict` resolves `m_def`."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import MetainfoParser

from .shapes import (
    FIELDS,
    Circle,
    Drawing,
    Shape,
    Square,
    Unrelated,
    annotate,
    built,
    convert,
    elements,
    from_dict_shapes,
    kind_sets,
    qualified,
    shape_data,
    summary,
)


@given(kind_sets, shape_data)
def test_build_maps_annotated_kinds(kinds, data):
    """summary(convert([(k1, x)]).shapes) = built(K, x), `K` the subclasses annotated under `k1`.

    built(K, x) lists (X, {field of X: its value in x}) for each X in `K`
    whose field is in `x`, in the definition order of the subclasses.
    The unannotated base defers to every subclass annotated under the active
    key; a subclass is built when its field is in the source, in the
    definition order of the subclasses.
    """
    annotate({(kind, 'k1') for kind in kinds})
    assert summary(convert([('k1', data)]).shapes) == built(kinds, data)


@given(kind_sets, shape_data, st.randoms(use_true_random=False))
def test_build_ignores_source_order(kinds, data, random):
    """summary(convert([(k1, x2)]).shapes) = summary(convert([(k1, x)]).shapes) for a permutation x2 of the keys of `x`.

    The order of the sections comes from the schema, not from the source.
    """
    annotate({(kind, 'k1') for kind in kinds})
    keys = list(data)
    random.shuffle(keys)
    permuted = {k: data[k] for k in keys}
    first = summary(convert([('k1', data)]).shapes)
    assert summary(convert([('k1', permuted)]).shapes) == first


@given(st.lists(elements, max_size=5))
def test_from_dict_keeps_type_per_element(items):
    """summary(MetainfoParser(data_object=Drawing()).from_dict({shapes: xs})) = [(X, {f: v}) for X, f, v in xs if v is not None].

    Each element of `xs` is {m_def: X, f: v}, with `f` the field of `X` (`name` for `Shape`).

    Each element's type comes from its own `m_def`, so one repeating
    subsection holds mixed subtypes in input order; elements without data
    are dropped (question 8).
    """
    field = {**FIELDS, Shape: 'name'}
    source = [
        {'m_def': qualified(kind), **({} if v is None else {field[kind]: v})}
        for kind, v in items
    ]
    target = MetainfoParser(data_object=Drawing())
    target.from_dict({'shapes': source})
    expected = [(kind.__name__, {field[kind]: v}) for kind, v in items if v is not None]
    assert summary(target.data_object.shapes) == expected


@pytest.mark.question('#19')
def test_sibling_subsections_share_subclasses():
    """Every annotated subclass lands in every sibling subsection of the base type.

    No annotation says which subclass belongs to which of `first`, `second`
    (FAIRmat-NFDI/nomad-file-parser#19).
    """
    annotate({(Circle, 'k1'), (Square, 'k1')})
    drawing = convert([('k1', {'radius': 1.0, 'side': 2.0})])
    expected = [('Circle', {'radius': 1.0}), ('Square', {'side': 2.0})]
    assert summary(drawing.first) == expected
    assert summary(drawing.second) == expected


@pytest.mark.parametrize(
    'elements, expected',
    [
        pytest.param(
            [{'m_def': 'no.such.Section', 'name': 'z'}],
            [('Shape', {'name': 'z'})],
            id='unknown-m-def-base-field',
            marks=pytest.mark.question(14),
        ),
        pytest.param(
            [{'m_def': 'no.such.Section', 'radius': 1.0}],
            [],
            id='unknown-m-def-subclass-field',
            marks=pytest.mark.question(14),
        ),
        pytest.param(
            [{'m_def': qualified(Unrelated), 'radius': 1.0}],
            [],
            id='m-def-outside-hierarchy',
            marks=pytest.mark.question(14),
        ),
        pytest.param(
            [{'m_def': qualified(Square), 'radius': 1.0}],
            [],
            id='field-of-other-subclass',
            marks=pytest.mark.question(15),
        ),
        pytest.param(
            [{'m_def': qualified(Circle), 'radius': 0.0}, {'name': ''}],
            [],
            id='falsy-only-subsection',
            marks=pytest.mark.question(17),
        ),
    ],
)
def test_from_dict_pinned(elements, expected):
    """Current type resolution asked about in `OPEN_QUESTIONS.md` (questions 14, 15, 17, per case)."""
    assert from_dict_shapes(elements) == expected
