import os
from collections import Counter

import pytest
from hypothesis import settings

settings.register_profile('dev', max_examples=25)
settings.register_profile('ci', max_examples=200, deadline=None)
settings.register_profile('big', max_examples=5000, deadline=None)
settings.load_profile(os.getenv('HYPOTHESIS_PROFILE', 'dev'))


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--questions',
        action='store_true',
        help='List the law tests with status and open questions instead of running them.',
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        'markers',
        'question(*refs): the test pins behaviour asked about in '
        '`tests/OPEN_QUESTIONS.md` (numbers) or in an issue (`#n`)',
    )


def status(item: pytest.Item) -> str:
    """`xfail` (we disagree), `pinned` (waits for an answer) or `law`."""
    if item.get_closest_marker('xfail'):
        return 'xfail'
    if item.get_closest_marker('question'):
        return 'pinned'
    return 'law'


def questions(item: pytest.Item) -> str:
    refs = {str(ref) for mark in item.iter_markers('question') for ref in mark.args}
    return ', '.join(
        sorted(refs, key=lambda ref: (ref.startswith('#'), int(ref.strip('#'))))
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """With `--questions`, replace the run by a table of the law tests."""
    if not config.getoption('questions'):
        return
    rows: dict[tuple, list[str]] = {}
    for item in items:
        if '/laws/' not in item.nodeid:
            continue
        function = getattr(item, 'originalname', item.name)
        doc = (item.function.__doc__ or '').strip().split('\n')[0]
        key = (item.path.stem, function, status(item), questions(item), doc)
        case = getattr(item, 'callspec', None)
        rows.setdefault(key, []).append(case.id if case else '')
    config.stash[ROWS] = rows
    config.hook.pytest_deselected(items=list(items))
    items[:] = []


ROWS = pytest.StashKey[dict]()
# Presentation order of the theme files in `tests/laws`.
THEMES = ['traversal', 'errors', 'parent_paths', 'repetition', 'subclasses', 'passes']


def pytest_terminal_summary(terminalreporter, config: pytest.Config) -> None:
    rows = config.stash.get(ROWS, None)
    if rows is None:
        return
    split = Counter(function for _, function, *_ in rows)
    write = terminalreporter.write_line
    write('')
    write('| Theme | Test | Status | Questions | Law |')
    write('|---|---|---|---|---|')

    def order(row):
        theme = row[0][0].removeprefix('test_')
        return THEMES.index(theme) if theme in THEMES else len(THEMES)

    for (stem, function, state, refs, doc), cases in sorted(rows.items(), key=order):
        name = f'{function}[{", ".join(cases)}]' if split[function] > 1 else function
        doc = doc.replace('|', '\\|')
        write(f'| {stem.removeprefix("test_")} | `{name}` | {state} | {refs} | {doc} |')


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if session.config.getoption('questions') and exitstatus == 5:
        session.exitstatus = 0
