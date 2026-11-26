"""Helpers of the law tests: how far a generated path reaches, and an in-memory parser."""

from typing import Any

from nomad_file_parser.mapping_parser import MappingParser, Path

from .paths import PROJECT, PathStr, Step, Tree


def prefix_value(obj: Tree, steps: list[Step]) -> Tree | None:
    """The value of the first steps of a path, as one segment; `obj` for none."""
    return Path(path=PathStr.from_steps(steps)).get_data(obj) if steps else obj


def all_steps(path: PathStr) -> list[Step]:
    """The steps of every segment, in order, as one list."""
    return [step for steps in path.segments for step in steps]


def depth(obj: Tree, path: PathStr) -> int:
    """How far the path reaches: the most steps whose value is neither None nor []."""
    steps = all_steps(path)
    reached = [
        k
        for k in range(len(steps) + 1)
        if prefix_value(obj, steps[:k]) not in (None, [])
    ]
    return max(reached, default=0)


def hits_projection(obj: Tree, path: PathStr) -> bool:
    """Whether some `[*]` of the path maps over a non-empty value."""
    steps = all_steps(path)
    return any(
        step == PROJECT and prefix_value(obj, steps[: i + 1]) not in (None, [])
        for i, step in enumerate(steps)
    )


class SourceParser(MappingParser):
    """A parser over an in-memory object, as the mapper needs one to run."""

    def from_dict(self, dct: dict[str, Any]) -> None:
        return super().from_dict(dct)  # type: ignore

    def load_file(self) -> Any:
        return super().load_file()

    def to_dict(self, **kwargs) -> dict[str | int, Any]:
        return super().to_dict(**kwargs)
