# Laws of the mapping parser

These property-based tests state the behaviour of the mapping parser as laws: equations that must hold for every generated source and path.
Behaviour whose intent is unclear is pinned as it is today and asked about in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md); behaviour we consider wrong is a strict `xfail`.

## Themes

| File | Theme | Questions |
|---|---|---|
| `test_traversal.py` | how the steps of a path compose: pipe, dot, projection, `@`, missing steps | 1 |
| `test_errors.py` | malformed and out-of-range input: purity of reads, parse errors, `default` | 2, 4, 5, 6 |
| `test_parent_paths.py` | relative paths `.q` under a parent path `p` | |
| `test_repetition.py` | sections built from lists by nested mappers, and `indices` | 7 to 12 |
| `test_subclasses.py` | which subclass the parser creates, and how `m_def` is resolved | 14, 15, 17, #19 |
| `test_passes.py` | several passes over one archive under `append`, `merge`, `replace` | 13, 16, 18 |
| `test_machinery.py` | checks on the generator and the reference evaluation, not on the parser | |

The other modules hold no laws: `strategies.py` generates sources and paths, `reference.py` evaluates them, `trees.py` and `shapes.py` provide the schemas of the mapper and subclass tests.

Every test is a **law** (it holds and we agree), **pinned** (current behaviour, marked `@pytest.mark.question(n)` and waiting for an answer) or **xfail** (strict, we disagree with the current behaviour).
The overview of all tests with their status and questions:

```bash
pytest tests/laws --questions
```

## Running

The Hypothesis profiles `dev` (25 examples, default), `ci` (200) and `big` (5000) are selected with `HYPOTHESIS_PROFILE` or `--hypothesis-profile`.

## Reading a law

Each test states its law as a formula in the first line of its docstring.
An equation between meanings, such as `eval(p | q) = eval(q) ∘ eval(p)`, means equal results on every source: `eval(p | q)(x) == eval(q)(eval(p)(x))` for all `x`.
Every variable is universally quantified over what the test's generator produces, so a law reads "for all generated x, p, q".
A clause starting with "when" restricts that domain, for example "`p0` without `[*]`", and the generator enforces the restriction.
`@example` pins individual cases of a law; they run first and in every profile.

| Token | Meaning |
|---|---|
| `Value` | object, list, leaf or `None`: the values of sources and of results alike (results include `[]` and nested lists) |
| `x`, `v` | a source value |
| `p`, `q`, `r` | paths, as lists of steps (`p0` a path without a projection); `k` a field step, `[i]` an index step, `s` a step of either kind |
| `eval` | `path → Value → Value`, curried: `eval(p)(x)` is `Path(path=p).get_data(x)`, and `eval(q)` can be passed on, as in `mapMaybe eval(q) xs` |
| `eval_d` | the same with a fallback `d`: `eval_d(p)(x)` is `Path(path=p).get_data(x, default=d)`; `eval = eval_None` |
| `None` | the failure value: `eval(p)(x) = None` when the path stops |
| `p ++ q` | syntax: the steps of `p` followed by those of `q`, rendered as one chain with `.` |
| `p \| q` | syntax: `p` and `q` as two chains joined by the pipe |
| `@` | the current node, the path without steps |
| `[*]` | the list projection |
| `.q under p` | the relative child `.q` of the parent `p` |
| `f ∘ g` | composition, right to left: `(f ∘ g)(x) = f(g(x))` |
| `mapMaybe f xs` | the list `[f(x) for x in xs if f(x) is not None]` |
| `v ! s` | the child of `v` at the field or index step `s`, `None` if there is none |
| `E(x)` | the domain of `x`: the set of paths that exist in `x` |
| `∈`, `∉`, `⇒`, `≤`, `≥` | membership, absence, implication, at most, at least |
| `p ↦ p'` | a wrangler that turns the generated `p` into `p'` |
| `p[:i]`, `p[i:]` | the first `i` steps of `p`, and the remaining ones |
| `P(…)` | the share of generated cases with a property |

The repetition laws add `M_K,L(x)` for the result of the mapper tree `C` → `S` → `E` with `indices=K` on `C` and `indices=L` on `S`, and `values(…)` for its `E` values as nested lists (see the module docstring of `test_repetition.py`).

## Defining equations

```text
eval(p | q)        = eval(q) ∘ eval(p)        the pipe composes whole values
eval(@)(x)         = x                        the current node
eval([*] ++ q)(xs) = mapMaybe eval(q) xs      a projection maps the rest of its chain
eval(s ++ q)(v)    = eval(q)(v ! s)           a step descends, None absorbs
.q under p         = p ++ q                   a relative child is prepended with `.`
```

`run` in `reference.py` evaluates a path by these equations alone; `test_path_matches_reference` checks that `Path` agrees with it.
`Path` adds one rule, a field on a list reads the last element (question 1), which `run` applies with `last_on_list=True`.
`E(x)` is prefix-closed (if `p ++ q ∈ E(x)`, then `p ∈ E(x)`), so it is a tree domain whose leaves are the paths that cannot be extended.

## Generators

Source and path come from one generator, `addresses`, which walks existing addresses of a generated source.
Wranglers then change the path: they leave the domain (`perturbed`), cut the path into parent and child (`splits`, `at_projection`) or into chains joined by `|` (`pipelines`), or make it unparseable (`malformed`).
`test_machinery.py` guards that the generated paths reach into the data, since paths that stop at the first step satisfy every law trivially.
