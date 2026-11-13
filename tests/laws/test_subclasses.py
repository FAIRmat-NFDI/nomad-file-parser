"""Section types: which subclass the parser creates, and how `from_dict` resolves `m_def`."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nomad_file_parser.mapping_parser import MetainfoParser

from .shapes import (
    FIELDS,
    KINDS,
    Drawing,
    Shape,
    Unrelated,
    annotate,
    built,
    convert,
    elements,
    from_dict_shapes,
    kind_sets,
    qualified,
    shape_data,
    shape_values,
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
    subsection holds mixed subtypes (polymorphism) in input order; elements
    without data are dropped and the later ones move up (question 8), so a
    position in the result is not a position in the input.
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


@pytest.mark.question(19)
@given(kind_sets, shape_data)
def test_sibling_subsections_share_subclasses(kinds, data):
    """summary(convert([(k1, x)]).first) = summary(convert([(k1, x)]).second) = built(K, x).

    Today's behaviour: every subclass annotated under the key lands in every
    sibling subsection of the base type, since no annotation says which
    subclass belongs to which of `first`, `second`. Agreed to be a defect;
    how a schema should declare the route is open
    (FAIRmat-NFDI/nomad-file-parser#19, question 19).
    """
    annotate({(kind, 'k1') for kind in kinds})
    drawing = convert([('k1', data)])
    assert summary(drawing.first) == built(kinds, data)
    assert summary(drawing.second) == built(kinds, data)


# m_def values that name no section of the `Shape` hierarchy.
UNRESOLVABLE = ['no.such.Section', qualified(Unrelated)]
names = st.sampled_from(['p', 'q'])
truthy_fields = st.dictionaries(st.sampled_from(sorted(FIELDS.values())), shape_values)


@pytest.mark.question(14)
@pytest.mark.xfail(
    strict=True, reason='an unresolvable m_def falls back to the base type'
)
@given(st.sampled_from(UNRESOLVABLE), st.none() | names, truthy_fields)
def test_unresolvable_m_def_raises(m_def, name, fields):
    """from_dict_shapes([{m_def: unresolvable, **fields}]) raises.

    Agreed (question 14), low priority: an `m_def` that names no section of
    the hierarchy (unknown, or a section outside it) is an error. Inside
    NOMAD it cannot happen, since the metainfo parser writes the `m_def`
    itself; it can when someone annotates a class that is not a NOMAD
    section. The exception type is left to the fix. Fails today: the element
    is built as the declared base type and subclass fields are lost
    silently.
    """
    element = {'m_def': m_def, **fields, **({} if name is None else {'name': name})}
    with pytest.raises(Exception):
        from_dict_shapes([element])


@pytest.mark.question(15)
@given(st.sampled_from(KINDS), st.none() | names, truthy_fields)
def test_element_keeps_only_fields_of_its_type(kind, name, fields):
    """from_dict_shapes([{m_def: X, **fields}]) = [(X, fields restricted to X)], or [] if none are left.

    Today's behaviour: a field of another subclass is dropped without a
    warning (`m_set` fails inside a bare `except`); if no field of `X` or of
    the base is left, the element is dropped as empty. It should not fail
    silently; whether it raises or warns is open (question 15).
    """
    element = {
        'm_def': qualified(kind),
        **fields,
        **({} if name is None else {'name': name}),
    }
    own = {f: v for f, v in element.items() if f in (FIELDS[kind], 'name')}
    expected = [(kind.__name__, own)] if own else []
    assert from_dict_shapes([element]) == expected


@pytest.mark.question(17)
@given(
    st.sampled_from(KINDS),
    st.sampled_from([0.0, 1.0]),
    st.none() | st.sampled_from(['', 'p']),
)
def test_falsy_values_are_data(kind, value, name):
    """from_dict_shapes([{m_def: X, f: v, name: n}]) = [(X, {f: v, name: n})] for falsy and truthy values alike.

    Agreed (question 17): `0.0` and `''` are data, as they are for the
    mapper (`is_not_value`), so an element holding only falsy values is kept.
    Fails today: `from_dict` treats them as empty (`or v`) and drops the
    element.
    """
    element = {
        'm_def': qualified(kind),
        FIELDS[kind]: value,
        **({} if name is None else {'name': name}),
    }
    fields = {f: v for f, v in element.items() if f != 'm_def'}
    assert from_dict_shapes([element]) == [(kind.__name__, fields)]
