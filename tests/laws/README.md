# Laws of the mapping parser

These property-based tests state the behaviour of the mapping parser as laws: equations that must hold for every generated source and path.
Behaviour whose intent is unclear is pinned as it is today and asked about in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md); behaviour we consider wrong is a strict `xfail`.

## Themes

| File | Theme | Questions |
|---|---|---|
| `test_traversal.py` | what one step does, and how steps compose: pipe, dot, projection, `@`, missing steps | 1 |
| `test_errors.py` | malformed and out-of-range input: purity of reads, parse errors, `default` | 2, 4, 5, 6 |
| `test_parent_paths.py` | relative paths `.q` under a parent path `p` | |
| `test_repetition.py` | sections built from lists by nested mappers, and `indices` | 7 to 12 |
| `test_subclasses.py` | which subclass the parser creates, and how `m_def` is resolved | 14, 15, 17, #19 |
| `test_passes.py` | several passes over one archive under `append`, `merge`, `replace` | 13, 16, 18 |
| `test_machinery.py` | a check on the generator, not on the parser | |

The other modules hold no laws: `paths.py` defines `PathStr` and `Tree`, `strategies.py` generates objects and paths, `support.py` measures how far a path reaches, `trees.py` and `shapes.py` provide the schemas of the mapper and subclass tests.

Every test is a **law** (it holds and we agree), **pinned** (current behaviour, marked `@pytest.mark.question(n)` and waiting for an answer) or **xfail** (strict, we disagree with the current behaviour).
The overview of all tests with their status and questions:

```bash
pytest tests/laws --questions
```

## Running

The Hypothesis profiles `dev` (25 examples, default), `ci` (200) and `big` (5000) are selected with `HYPOTHESIS_PROFILE` or `--hypothesis-profile`.

## Reading a law

Each test states its law as a formula in the first line of its docstring, in terms of the mapping parser itself: `Path(p).get_data(obj)` is the value the parser reads at path `p` from the object `obj`, exactly what the test executes as `Path(path=p).get_data(obj)`.
An equation such as `Path(p | q).get_data(obj) = Path(q).get_data(Path(p).get_data(obj))` holds for every generated `obj`, `p` and `q`.
A clause starting with "when" restricts that domain, for example "when `p` opens no projection", and the generator enforces the restriction.
Pinned cases are listed with their expected value per case.

| Token | Meaning |
|---|---|
| `Tree` | what a path is read from and what it returns: an object (`dict`), a list, or a leaf (`bool`, `int`, `float`, `str`, `None`) |
| `obj`, `v`, `vs` | a tree, a node in it, a list node |
| `None` | also the failure value: a path that cannot be followed gives `None`, so a stored `None` and a missing path read the same |
| `p`, `q`, `r` | paths, written as `PathStr`: segments joined by `\|`, each one steps joined by `.` (`p0` a path that opens no projection) |
| `k`, `[i]`, `[*]` | a field step, an index step, the list projection; index and projection steps attach without a dot (`p[0]`) |
| `p.q` | the dot: `q` continues the segment of `p`, inside an open projection |
| `p \| q` | the pipe: `q` is applied to the whole value of `p` |
| `@`, `.p` | the current node; `p` relative to a parent path |
| `.q under p` | the relative child `.q` of the parent `p` |
| `E(obj)` | the paths that exist in `obj` |
| `∈`, `∉`, `⇒`, `≤`, `≥` | membership, absence, implication, at most, at least |
| `p[:i]`, `p[i:]` | the first `i` steps of `p`, and the remaining ones |
| `P(…)` | the share of generated cases with a property |

The repetition laws add `M_K,L(obj)` for the result of the mapper tree `C` → `S` → `E` with `indices=K` on `C` and `indices=L` on `S`, and `values(…)` for its `E` values as nested lists (see the module docstring of `test_repetition.py`).

## How the laws fix the behaviour

The step laws in `test_traversal.py` state what one field, index and projection step does on any node.
The composition laws state how steps combine: the pipe always nests, the dot nests while no projection is open and maps per element after one, `@` is neutral, and a missing step makes every extension missing.
Together they determine the value of every path of the fragment, so no separate model of the parser is needed.
`E(obj)` is prefix-closed (if `p.q ∈ E(obj)`, then `p ∈ E(obj)`), so it is a tree domain whose leaves are the paths that cannot be extended.

## Paths in the code

`PathStr` (`paths.py`) is a `str` that parses: its constructor checks the format with the parser `Path` uses, so a malformed path fails when it is built, not as a `None` later.
`p | q`, `p.dot(q)` and `p.relative()` build the composed paths of the laws.
Only the `default=` laws use plain strings, since they need paths that do not parse.

## Generators

Object and path come from one generator, `walks`, which walks existing paths of a generated object.
Wranglers then change the path: they leave the domain (`perturbed`), cut the path into parent and child (`splits`, `at_projection`) or into segments joined by `|` (`pipelines`), or make it unparseable (`malformed`).
`test_machinery.py` guards that the generated paths reach into the data, since paths that stop at the first step satisfy every law trivially.
