"""How the laws evaluate paths and run the parser.

`run` evaluates a path by the defining equations in `README.md`; `get` evaluates it
with `Path`, the implementation under test; `SourceParser` runs a mapper on an
in-memory source.
"""

from typing import Any

from nomad_file_parser.mapping_parser import MappingParser, Path

from .strategies import PROJECT, Step


def run_chain(chain: list[Step], value: Any, last_on_list: bool = False) -> Any:
    """Evaluate one chain by the defining equations, by recursion on its steps:

        eval([])(v)       = v
        eval([*] ++ q)(v) = mapMaybe eval(q) v   if v is a list, else None
        eval(s ++ q)(v)   = eval(q)(v ! s)

    where v ! s is the child of `v` at the field or index step `s`, and
    None when there is none: `v` is not an object (for `k`) or not a list
    (for `[i]`), or the key is missing or the index out of range. So `None`
    absorbs along a chain and a projection captures the rest of it.
    `last_on_list` adds `Path`'s rule eval(k)(xs) = eval(k)(xs[-1]) for a
    field on a non-empty list.
    """
    if not chain:
        return value
    step, rest = chain[0], chain[1:]
    if step == PROJECT:
        if not isinstance(value, list):
            return None
        results = (run_chain(rest, x, last_on_list) for x in value)
        return [r for r in results if r is not None]
    if isinstance(step, int):
        found = isinstance(value, list) and -len(value) <= step < len(value)
        return run_chain(rest, value[step] if found else None, last_on_list)
    if last_on_list and isinstance(value, list):
        value = value[-1] if value else None
    found = isinstance(value, dict)
    return run_chain(rest, value.get(step) if found else None, last_on_list)


def run(pipeline: list[list[Step]], value: Any, last_on_list: bool = False) -> Any:
    """Evaluate c1 | … | cm by the pipe law: eval(cm) ∘ … ∘ eval(c1)."""
    for chain in pipeline:
        value = run_chain(chain, value, last_on_list)
    return value


def get(path: str, source: Any) -> Any:
    """eval(path)(source) as evaluated by `Path`, the implementation under test."""
    return Path(path=path).get_data(source)


def depth(source: Any, chain: list[Step]) -> int:
    """max {k : eval(chain[:k])(source) ∉ {None, []}}, how far the path reaches."""
    reached = [
        k
        for k in range(len(chain) + 1)
        if run_chain(chain[:k], source, True) not in (None, [])
    ]
    return max(reached, default=0)


def hits_projection(source: Any, chain: list[Step]) -> bool:
    """Whether some `[*]` in the chain maps over a non-empty result."""
    return any(
        step == PROJECT and run_chain(chain[: i + 1], source, True) not in (None, [])
        for i, step in enumerate(chain)
    )


class SourceParser(MappingParser):
    """A parser over an in-memory source, as the mapper needs one to run."""

    def from_dict(self, dct: dict[str, Any]) -> None:
        return super().from_dict(dct)  # type: ignore

    def load_file(self) -> Any:
        return super().load_file()

    def to_dict(self, **kwargs) -> dict[str | int, Any]:
        return super().to_dict(**kwargs)
