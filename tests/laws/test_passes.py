"""Several passes over one archive: update modes `append`, `merge`, `replace`."""

import pytest
from hypothesis import given

from .shapes import (
    Circle,
    Square,
    Triangle,
    annotate,
    built,
    convert,
    full_shape_data,
    kind_sets,
    summary,
)


@given(kind_sets, kind_sets, full_shape_data)
def test_append_passes_concatenate(kinds1, kinds2, data):
    """summary(convert([(k1, x), (k2, x)], 'append').shapes) = built(K1, x) + built(K2, x).

    `K1` and `K2` are the subclasses annotated under `k1` and `k2`.
    A second pass under another key adds its subclasses after the first
    pass's, so heterogeneous subtypes collect in one list. Every field is in
    the source: an annotated subclass without data in the first pass leaves
    a misaligned element (`test_append_pass_reuses_misaligned_element`).
    """
    annotate(
        {(kind, 'k1') for kind in kinds1} | {(kind, 'k2') for kind in kinds2},
        update_mode='append',
    )
    drawing = convert([('k1', data), ('k2', data)], update_mode='append')
    assert summary(drawing.shapes) == built(kinds1, data) + built(kinds2, data)


@pytest.mark.question(13)
def test_merge_across_subclasses_keeps_first():
    """summary(convert([(k1, x), (k2, x)], 'merge').shapes) = [('Circle', {radius: 1.0})].

    With `Circle` under `k1`, `Square` under `k2` and x = {radius: 1.0, side: 2.0}.
    The second pass aligns `Square` with the existing `Circle` at position 0;
    the type of the first pass wins and `side` is lost (question 13).
    """
    annotate({(Circle, 'k1'), (Square, 'k2')}, update_mode='merge')
    data = {'radius': 1.0, 'side': 2.0}
    drawing = convert([('k1', data), ('k2', data)], update_mode='merge')
    assert summary(drawing.shapes) == [('Circle', {'radius': 1.0})]


@pytest.mark.question(16)
@pytest.mark.parametrize('mode', ['append', 'merge', 'replace'])
def test_scalar_passes_overwrite(mode):
    """convert([(k1, {title: 'old'}), (k2, {title: 'new'})], mode).title = 'new' for every mode.

    A second pass overwrites a scalar under every mode (question 16).
    """
    annotate(set())
    drawing = convert([('k1', {'title': 'old'}), ('k2', {'title': 'new'})], mode)
    assert drawing.title == 'new'


@pytest.mark.question(18)
@pytest.mark.xfail(strict=True, reason='a later pass reuses a misaligned element')
def test_append_pass_reuses_misaligned_element():
    """summary(convert([(k1, x), (k2, x)], 'append').shapes) = [('Triangle', {height: 1.0})].

    With `Circle` and `Triangle` under `k1`, nothing under `k2` and
    x = {height: 1.0}.
    Pass 1 drops the empty `Circle` from the archive but keeps it in the
    parser's intermediate data, so position 0 holds `Circle` there and
    `Triangle` in the archive. Pass 2 replays the data by position, reuses
    the `Triangle` instance at 0 and reassigns its `m_def` to `Circle`: the
    result is [Triangle with `m_def` Circle, Triangle {height: 1}]
    (question 18).
    """
    annotate({(Circle, 'k1'), (Triangle, 'k1')}, update_mode='append')
    data = {'height': 1.0}
    drawing = convert([('k1', data), ('k2', data)], update_mode='append')
    assert [(type(s).__name__, s.m_def.name) for s in drawing.shapes] == [
        ('Triangle', 'Triangle')
    ]
    assert summary(drawing.shapes) == [('Triangle', {'height': 1.0})]
