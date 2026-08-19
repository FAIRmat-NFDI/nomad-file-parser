from nomad_file_parser.text_parser import Quantity, TextParser


def test_visualizer_does_not_highlight_when_no_leaf_quantities_are_parsed(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('entire file')

    html = TextParser(str(mainfile), quantities=[]).visualize().to_html()

    assert '<mark' not in html


def test_text_visualizer_does_not_highlight_subparser_scopes(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nSTART\nparsed value\nEND\nafter\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'block',
                r'START\n([\s\S]+?)END',
                sub_parser=TextParser(quantities=[]),
            )
        ],
    )

    html = parser.get('block').visualize(context_lines=0).to_html()

    assert '<mark' not in html


def test_root_text_parser_visualizer_marks_only_parsed_values(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nenergy = 1.5\nafter\n')
    parser = TextParser(
        str(mainfile), quantities=[Quantity('energy', r'energy\s*=\s*([\d.]+)')]
    )

    html = parser.visualize(context_lines=0, key='energy').to_html()

    assert '<mark data-byte-start="16" data-byte-end="19">1.5</mark>' in html
    assert 'before' in html
    assert 'after' in html


def test_text_visualizer_marks_only_leaves_and_colors_subparser_groups(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text(
        'A_START\nfirst = 1\nA_END\nB_START\nsecond = 2\nB_END\nroot = 3\n'
    )
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section_a',
                r'A_START\n([\s\S]+?)A_END',
                sub_parser=TextParser(
                    quantities=[Quantity('first', r'first\s*=\s*(\d+)')]
                ),
            ),
            Quantity(
                'section_b',
                r'B_START\n([\s\S]+?)B_END',
                sub_parser=TextParser(
                    quantities=[Quantity('second', r'second\s*=\s*(\d+)')]
                ),
            ),
            Quantity('root', r'root\s*=\s*(\d+)'),
        ],
    )

    html = parser.visualize().to_html()

    assert (
        '<mark data-byte-start="16" data-byte-end="17" style="background-color:#fff59d;">1</mark>'
        in html
    )
    assert (
        '<mark data-byte-start="41" data-byte-end="42" style="background-color:#b2dfdb;">2</mark>'
        in html
    )
    assert '<mark data-byte-start="56" data-byte-end="57">3</mark>' in html
    assert 'A_START\n<mark' not in html
    assert 'B_START\n<mark' not in html


def test_visualizer_show_opens_a_browser_tab(tmp_path, monkeypatch):
    mainfile = tmp_path / 'output.txt'
    destination = tmp_path / 'visualizations' / 'parsed-block.html'
    mainfile.write_text('parsed value')
    opened = []
    monkeypatch.setattr('webbrowser.open_new_tab', opened.append)

    result = TextParser(str(mainfile), quantities=[]).show_visualization(
        path=destination
    )

    assert result == destination
    assert opened == [destination.as_uri()]
    assert 'parsed value' in destination.read_text()


def test_visualizer_show_uses_a_source_adjacent_directory_by_default(
    tmp_path, monkeypatch
):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('parsed value')
    monkeypatch.setattr('webbrowser.open_new_tab', lambda _: True)

    result = TextParser(str(mainfile), quantities=[]).show_visualization()

    assert result.parent == tmp_path / '.nomad-visualizations'
    assert result.is_file()
