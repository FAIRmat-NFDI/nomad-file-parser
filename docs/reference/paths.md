# Path syntax and semantics

Mapping annotations and `Path` objects address data in the dictionary representation of a parsed file.
A path is a [JMESPath](https://jmespath.org/specification.html){:target="_blank" rel="noopener"} expression, optionally preceded by a `.` that makes it relative to the path of the enclosing section.
This page describes how such a path is evaluated, with emphasis on the two ways of composing steps, `.` and `|`, since they behave differently once a path selects several elements.

All examples below are evaluated on the following source, the shape that `XMLParser` produces for repeated elements:

```python
data = {
    'calculation': [
        {'energy': {'total': -1.0}, 'scf': [{'e': -0.9}, {'e': -1.0}]},
        {'energy': {'total': -2.0}, 'scf': [{'e': -1.9}]},
    ],
    'i': [
        {'@name': 'program', '__value': 'VASP'},
        {'@name': 'version', '__value': '6.4'},
    ],
}
```

## Steps

A path is built from steps applied from left to right.
A field step `energy` looks up a key in a dictionary, an index step `[0]` or `[-1]` selects one element of a list, and `@` stands for the current value without moving.
A step that cannot be taken, such as a missing key, an index beyond the end of the list, or a field applied to a number, yields `None`, and every later step on `None` yields `None` again.
A path therefore returns `None` both when the data are absent and when they are present but hold `None`; the two cases cannot be told apart from the result.

| Path | Result |
|------|--------|
| `calculation[0].energy.total` | `-1.0` |
| `calculation[0].missing` | `None` |
| `@` | the whole source |

## Projections

Some steps select several elements at once: the list projection `[*]`, slices such as `[0:2]`, and filters such as `[?"@name"=='version']`.
Such a step opens a *projection*: the remaining steps of the expression are applied to every selected element separately, and the results are collected into a list.
Elements for which the remaining steps yield `None` are dropped from that list rather than reported.

A slice whose bounds lie beyond the end of the list yields `None` in `Path` (`calculation[0:5]`, `calculation[-5:]`), whereas JMESPath clamps the bounds to the list and returns the available elements; a slice starting beyond the end yields `[]` in both.

| Path | Result |
|------|--------|
| `calculation[*].energy.total` | `[-1.0, -2.0]` |
| `calculation[*].scf[-1].e` | `[-1.0, -1.9]`, the last SCF step of each calculation |
| `calculation[*].scf[*].e` | `[[-0.9, -1.0], [-1.9]]`, one list per calculation |
| `calculation[*].energy[0]` | `[]`, since `[0]` is applied to each `energy` dictionary |

## The two delimiters

The `.` between steps continues the current expression.
Outside a projection it simply moves one level down.
Inside a projection it belongs to the projection, so the step after it is applied per element, as in the examples above.

The pipe `|` instead evaluates its right-hand side on the complete result of its left-hand side.
It therefore closes a projection: after `|`, a list produced by a projection is an ordinary value again and can be indexed as a whole.
This is why filters are usually followed by `| [0]` when a single match is expected:

| Path | Result |
|------|--------|
| `calculation[*].energy \| [0]` | `{'total': -1.0}`, the first calculation's energy |
| `calculation[*].energy.total \| [1]` | `-2.0` |
| `i[?"@name"=='version'] \| [0].__value` | `'6.4'` |
| `i[?"@name"=='version'][0].__value` | `[]`, since `[0]` is applied to each match |

For paths without a projection the two delimiters agree: `a.b` and `a | b` give the same result.
`@` leaves a path unchanged on either side of a pipe (`@ | p` and `p | @` both equal `p`) and at the start of a dotted path (`@.p` equals `p`).
A dot followed by a bracket is not a step delimiter but starts JMESPath's multi-select syntax: `@.[*]` wraps the value in a list instead of projecting it, and `@.[0]` does not parse. Index and projection steps are therefore written directly after the preceding step, as in `calculation[0]`.

## Fields on lists

JMESPath gives `None` for a field step applied to a list.
`Path` instead applies the field to the last element of the list, so that a path written for a single element also reads a repeated one:

| Path | `Path` | JMESPath |
|------|--------|----------|
| `calculation.energy.total` | `-2.0` | `None` |
| `calculation[*] \| energy` | `{'total': -2.0}` | `None` |

An empty list still gives `None`.
When all elements are wanted, use a projection (`calculation[*].energy`); when a specific one is wanted, use an index.

## Relative paths and inheritance

A path that starts with `.` is relative to the path of its parent, which is the enclosing section's annotation for a schema annotation and the `parent` attribute for a `Path` object.
The parent's path is prepended with a `.` delimiter: a child `.energy.total` under the parent `calculation[*]` has the absolute path `calculation[*].energy.total`.
`.@` refers to the parent's value itself, and an absolute path (without the leading `.`) is always resolved from the root of the source, regardless of the parent.

Because the join uses `.`, a parent that opens a projection applies its children per element, and a parent without a projection behaves as if its result were the new root: for such a parent `p`, the child `.q` gives the same result as evaluating `q` on the result of `p`.
The mapper follows the same rule when it fills sections: if a section's source path resolves to a list, its children are evaluated once per element, which is how repeating subsections are instantiated.

The leading `.` is recognised only at the start of a path and after whitespace.
Inside a function call it is not stripped, so `length(.calculation)` does not parse and yields `None`; a relative path cannot be passed to a JMESPath function.
A path consisting of `.` alone has no steps and also yields `None`; use `.@` for the parent's value.

`Path.get_data` returns its `default` keyword argument only when the expression cannot be evaluated, for example on a syntax error; a missing path returns `None`.
