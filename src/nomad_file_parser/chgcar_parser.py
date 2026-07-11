import re

import numpy as np

from .file_parser import FileParser


class CHGCARFileParser(FileParser):
    """Reader for VASP CHGCAR-format charge-density grids.

    A CHGCAR file starts with a POSCAR-style structure header followed by one or
    more grid blocks. Each block is introduced by a line with the three grid
    dimensions and continues with the volumetric values in row-major order until
    ``nx * ny * nz`` values have been read. Spin-polarised calculations emit
    several blocks (total density, magnetisation, ...), so the parser exposes a
    list of arrays under the ``values`` key, each reshaped to its grid.
    """

    def parse(self, key: str | None = None) -> None:
        if self._results is None:
            self._results = {}

        values = []
        re_grid = re.compile(r' *\d+ +\d+ +\d+\s+')
        with self.open_mainfile_obj() as f:
            grid = None
            n_points = 0
            charge_density: list[float] = []
            for line in f:
                if not line.strip():
                    grid = []
                if grid is None:
                    # still inside the structure header
                    continue

                if re_grid.match(line) and n_points == 0:
                    grid = [int(i) for i in line.strip().split()]
                    n_points = grid[0] * grid[1] * grid[2]
                elif len(charge_density) < n_points:
                    charge_density.extend(float(v) for v in line.strip().split())

                if charge_density and len(charge_density) == n_points:
                    values.append(
                        np.reshape(np.array(charge_density, np.float64), grid)
                    )
                    grid = []
                    n_points = 0
                    charge_density = []

        self._results['values'] = values
