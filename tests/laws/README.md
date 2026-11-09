# Laws of the mapping parser

These property-based tests state the behaviour of the mapping parser as laws: equations that must hold for every generated object and path.
`Path` passes projections, pipes and filters to the `jmespath` package unchanged. The JMESPath specification already defines how these behave, so the laws do not test them again; they are listed under [Standard JMESPath behaviour](#standard-jmespath-behaviour-not-tested-here). The laws do test the steps that `Path` reimplements: fields, indices and slices.
Behaviour whose intent is unclear is pinned as it is today and asked about in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md); behaviour we consider wrong is a strict `xfail`.

## Themes

| File | Theme | Questions |
|---|---|---|
| `test_steps.py` | the steps `Path` reimplements: fields (including a field on a list), indices and slices | 1, 2, 3 |
| `test_errors.py` | malformed, relative and out-of-range input: purity of reads, functions, `default` | 2, 4, 5, 6 |
| `test_parent_paths.py` | relative paths `.q` under a parent path `p`, and `.@` | |
| `test_repetition.py` | sections built from lists by nested mappers, and `indices` | 7 to 12 |
| `test_subclasses.py` | which subclass the parser creates, and how `m_def` is resolved | 14, 15, 17, 19 |
| `test_passes.py` | several passes over one archive under `append`, `merge`, `replace` | 13, 16, 18 |
| `test_machinery.py` | a check on the generator, not on the parser | |

The other modules hold no laws: `paths.py` defines `PathStr` and `Tree`, `strategies.py` generates objects and paths, `support.py` measures how far a path reaches, `trees.py` and `shapes.py` provide the schemas of the mapper and subclass tests.

Every test is a **law** (it holds and we agree), **pinned** (today's behaviour, marked `@pytest.mark.question(n)` while the question is open) or **xfail** (strict: it asserts the agreed behaviour and fails until the code does it; once fixed it passes and the mark is removed).
The overview of all tests with their status and questions:

```bash
pytest tests/laws --questions
```

## Running

The law tests are skipped in a plain `pytest` run, since they take longer and are meant for the end of a pull request; `--laws` runs them.
In CI they run only in the `laws` job, which is started by hand (`workflow_dispatch` of the `install-and-test-workflow`).

```bash
pytest tests/laws --laws
HYPOTHESIS_PROFILE=ci pytest tests/laws --laws
```

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
| `k`, `[i]`, `[*]`, `[?k==v]` | a field step, an index step, the list projection, a filter; the bracketed steps attach without a dot (`p[0]`) |
| `p.q` | the dot: `q` continues the segment of `p`, inside an open projection |
| `p \| q` | the pipe: `q` is applied to the whole value of `p` |
| `@`, `.p` | the current node; `p` relative to a parent path |
| `.q under p` | the relative child `.q` of the parent `p` |
| `E(obj)` | the paths that exist in `obj` |
| `∈`, `∉`, `⇒`, `<=`, `>=` | membership, absence, implication, at most, at least |
| `p[:i]`, `p[i:]` | the first `i` steps of `p`, and the remaining ones |
| `P(…)` | the share of generated cases with a property |

The mapper laws name the helpers that run the mapper: `tree(obj, outer=K, inner=L)` runs the mapper tree `C` → `S` → `E` with `indices=K` on `C` and `indices=L` on `S`, and `values(…)` reads its `E` values as nested lists (`trees.py`); `convert(passes, update_mode)` runs the `MetainfoParser` once per `(key, x)` pass on one `Drawing`, and `summary(sections)` lists the type and set values of each section (`shapes.py`).

## Standard JMESPath behaviour (not tested here)

`Path` evaluates paths with a subclass of the JMESPath interpreter that reimplements four visitor methods: `visit_field`, `visit_index`, `visit_slice` and `visit_index_expression` (`mapping_parser.py`).
Fields, indices and slices are therefore tested (`test_steps.py`).
Everything else runs JMESPath's own code, so the specification defines it and these tests do not repeat it.
The laws below were tested in earlier versions of this suite and held; they are kept here as the reference for how paths compose.

| Law | Meaning |
|---|---|
| `Path([*]).get_data(v) = [x for x in v if x is not None]` when `v` is a list, else `None` | a projection collects the elements and drops `None` |
| `Path(p \| q).get_data(obj) = Path(q).get_data(Path(p).get_data(obj))` | the pipe nests, unconditionally |
| `Path(p.q).get_data(obj) = Path(p \| q).get_data(obj)` when `p` opens no projection | the dot nests like the pipe while no projection is open |
| `Path(p0[*].q).get_data(obj) = [r for o in Path(p0).get_data(obj) if (r := Path(q).get_data(o)) is not None]` when `p0` opens no projection | after a projection the dot applies `q` per element |
| `Path(@ \| p).get_data(obj) = Path(p).get_data(obj) = Path(p \| @).get_data(obj)`, and the same for `@.p` when `p` starts with a field | `@` is neutral; `p.@` is not valid, `@.[*]` is a multi-select |
| `Path(p).get_data(obj) = None ⇒ Path(p.q).get_data(obj) = None` | a missing step makes every extension missing, so `E(obj)` is prefix-closed |
| `Path(vs[?k==v]).get_data(obj) = [o for o in vs if o is not None and same(Path(k).get_data(o), v)]`, `None` on a non-list | a filter selects elements, compares by type and value (`1` is not `true`), and a missing key matches `null` |
| `Path(p0[?f].q)` and `Path(p0[?f] \| q)` as for `[*]` | a filter opens a projection like `[*]`, and `\|` closes it |

A projection opened by `[*]` or a filter stays open up to the next `|` (`PathStr.opens_projection`).
With `p0` projecting, a further `[*]` nests inside it: on `{c: [[{}]]}`, `c[*][*].a` gives `[[]]`, while mapping `a` over the value of `c[*]` gives `[]`.
The parsers rely on the pipe to close a filter, as in `vasp.py`: on the elements `{"@name": "program", "__value": "VASP"}`, `{"@name": "version", …}` and `{"@name": "program", "__value": "other"}` under `i`:

| Path | Value |
|---|---|
| `i[?"@name"=='program']` | both `program` elements |
| `i[?"@name"=='program'][0]` | `[]`, since `[0]` is applied to each match |
| `i[?"@name"=='program'] \| [0]` | the first `program` element |
| `i[?"@name"=='program'] \| [0].__value` | `'VASP'` |
| `i[?"@name"=='program'].__value \| [0]` | `'VASP'` |
| `i[?"@name"=='none'] \| [0]` | `None` |

The field rule of `Path` also applies inside a filter condition, so `v[?a==`1`]` selects an element `[{'a': 1}]` (question 1, pinned in `test_steps.py`).

## Paths in the code

`PathStr` (`paths.py`) is a `str` that parses: its constructor checks the format with the parser `Path` uses, so a malformed path fails when it is built, not as a `None` later.
`p | q`, `p.dot(q)` and `p.relative()` build the composed paths of the laws.
Only the `default=` laws use plain strings, since they need paths that do not parse.

## Generators

Object and path come from one generator, `walks`, which walks existing paths of a generated object.
Wranglers then change the path: they leave the domain (`perturbed`), cut the path into parent and child (`splits`, `at_projection`) or into segments joined by `|` (`pipelines`), or make it unparseable (`malformed`).
`test_machinery.py` guards that the generated paths reach into the data, since paths that stop at the first step satisfy every law trivially.
