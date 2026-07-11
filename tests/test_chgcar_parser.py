import numpy as np
from pytest import approx

from nomad_file_parser import CHGCARFileParser

MAINFILE = 'tests/data/parsers/vasp_chgcar/CHGCAR'


def test_chgcar_grid_blocks():
    """Each grid block is read into its own reshaped array (total, magnetisation, ...)."""
    parser = CHGCARFileParser()
    parser.mainfile = MAINFILE

    values = parser.get('values')
    assert len(values) == 2
    assert all(isinstance(v, np.ndarray) and v.shape == (2, 2, 2) for v in values)

    # row-major fill within each block, augmentation-occupancy lines skipped
    assert values[0][0][0][0] == approx(0.0)
    assert values[0][1][1][1] == approx(7.0)
    assert values[1][0][0][0] == approx(10.0)
    assert values[1][1][1][1] == approx(17.0)
