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

    html = parser.visualize(key='energy').to_html()

    assert (
        '<mark data-byte-start="16" data-byte-end="19" style="background-color:#fff59d;" title="energy">1.5</mark>'
        in html
    )
    assert 'before' in html
    assert 'after' in html


def test_context_lines_selects_a_compact_view(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nenergy = 1.5\nafter\n')
    parser = TextParser(
        str(mainfile), quantities=[Quantity('energy', r'energy\s*=\s*([\d.]+)')]
    )

    html = parser.visualize(context_lines=0).to_html()

    assert 'energy = ' in html
    assert 'before' not in html
    assert 'after' not in html


def test_context_lines_uses_leaf_ranges_when_ancestors_cover_the_file(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nvalue = 1\nafter\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                r'([\s\S]+)',
                sub_parser=TextParser(
                    quantities=[Quantity('value', r'value\s*=\s*(\d+)')]
                ),
            )
        ],
    )

    html = parser.visualize(context_lines=0).to_html()

    assert 'value = ' in html
    assert 'before' not in html
    assert 'after' not in html


def test_key_limits_highlights_and_context_to_the_selected_quantity(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nfirst = 1\nsecond = 2\nafter\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity('first', r'first\s*=\s*(\d+)'),
            Quantity('second', r'second\s*=\s*(\d+)'),
        ],
    )

    visualizer = parser.visualize(key='second', context_lines=0)

    assert [block.quantity_name for block in visualizer.blocks] == ['TextParser.second']
    html = visualizer.to_html()
    assert 'second = ' in html
    assert 'first = ' not in html
    assert 'before' not in html
    assert 'after' not in html


def test_text_visualizer_marks_leaf_quantities_by_default(tmp_path):
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
        '<mark data-byte-start="16" data-byte-end="17" style="background-color:#fff59d;" title="first">1</mark>'
        in html
    )
    assert (
        '<mark data-byte-start="41" data-byte-end="42" style="background-color:#b2dfdb;" title="second">2</mark>'
        in html
    )
    assert (
        '<mark data-byte-start="56" data-byte-end="57" style="background-color:#bbdefb;" title="root">3</mark>'
        in html
    )
    blocks = parser.visualize().blocks
    assert {block.quantity_name for block in blocks} == {
        'TextParser.section_a.first',
        'TextParser.section_b.second',
        'TextParser.root',
    }


def test_visualizer_labels_nested_leaf_quantities(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('BEGIN\nvalue = 1\nEND\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                [r'BEGIN', r'END'],
                sub_parser=TextParser(
                    quantities=[Quantity('value', r'value\s*=\s*(\d+)')]
                ),
            )
        ],
    )
    parser.line_parsing = True
    blocks = parser.visualize(leaves_only=False).blocks

    value_block = next(block for block in blocks if block.start == 14)
    assert value_block.quantity_name == 'TextParser.section.value'
    section_block = next(
        block
        for block in parser.visualize(leaves_only=False).blocks
        if block.quantity_name == 'TextParser.section'
    )
    assert (section_block.start, section_block.end) == (0, 19)


def test_visualize_can_show_all_quantities_with_transparent_ancestors(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('BEGIN\nINNER\nvalue = 1\nEND_INNER\nEND\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                [r'BEGIN', r'END'],
                sub_parser=TextParser(
                    quantities=[
                        Quantity(
                            'subsection',
                            [r'INNER', r'END_INNER'],
                            sub_parser=TextParser(
                                quantities=[Quantity('value', r'value\s*=\s*(\d+)')]
                            ),
                        )
                    ]
                ),
            )
        ],
    )
    parser.line_parsing = True

    blocks = parser.visualize(leaves_only=False).blocks

    assert {(block.quantity_name, block.depth) for block in blocks} == {
        ('TextParser.section', 0),
        ('TextParser.section.subsection', 1),
        ('TextParser.section.subsection.value', 2),
    }
    html = parser.visualize(leaves_only=False).to_html()
    assert 'background-color:rgba(255, 245, 157, 0.35);' in html
    assert 'background-color:rgba(178, 223, 219, 0.675);' in html


def test_visualize_shows_leaf_quantities_by_default(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('BEGIN\nvalue = 1\nEND\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                [r'BEGIN', r'END'],
                sub_parser=TextParser(
                    quantities=[Quantity('value', r'value\s*=\s*(\d+)')]
                ),
            )
        ],
    )
    parser.line_parsing = True

    blocks = parser.visualize().blocks

    assert [block.quantity_name for block in blocks] == ['TextParser.section.value']


def test_visualize_none_depth_omits_empty_subparser_scopes(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('BEGIN\nno values\nEND\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                [r'BEGIN', r'END'],
                sub_parser=TextParser(quantities=[]),
            )
        ],
    )
    parser.line_parsing = True

    assert parser.visualize().blocks == []


def test_repeated_quantity_matches_keep_the_same_quantity_name(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('value = 1\nvalue = 2\n')
    parser = TextParser(
        str(mainfile),
        quantities=[Quantity('value', r'value\s*=\s*(\d+)', repeats=True)],
    )

    blocks = parser.visualize().blocks

    assert len(blocks) == 2
    assert blocks[0].quantity_name == blocks[1].quantity_name == 'TextParser.value'
    assert blocks[0].quantity_name == blocks[1].quantity_name


def test_line_parser_records_only_leaf_capture_groups_for_visualization(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nenergy = 1.5\nafter\n')
    parser = TextParser(
        str(mainfile), quantities=[Quantity('energy', r'energy\s*=\s*([\d.]+)')]
    )
    parser.line_parsing = True

    html = parser.visualize().to_html()

    assert (
        '<mark data-byte-start="16" data-byte-end="19" style="background-color:#fff59d;" title="energy">1.5</mark>'
        in html
    )


def test_line_parser_highlights_complete_blocks_without_capture_groups(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('before\nSTART\nparsed value\nFINISHED\nafter\n')
    parser = TextParser(
        str(mainfile),
        quantities=[Quantity('block', [r'START', r'FINISHED'], convert=False)],
    )
    parser.line_parsing = True

    html = parser.visualize().to_html()

    assert (
        '<mark data-byte-start="7" data-byte-end="34" style="background-color:#fff59d;" title="block">START\nparsed value\nFINISHED</mark>'
        in html
    )


def test_line_parser_visualizer_parses_nested_blocks(tmp_path):
    mainfile = tmp_path / 'output.txt'
    mainfile.write_text('BEGIN\nvalue = 1\nEND\n')
    parser = TextParser(
        str(mainfile),
        quantities=[
            Quantity(
                'section',
                [r'BEGIN', r'END'],
                sub_parser=TextParser(
                    quantities=[Quantity('value', r'value\s*=\s*(\d+)')]
                ),
            )
        ],
    )
    parser.line_parsing = True

    html = parser.visualize().to_html()

    assert (
        '<mark data-byte-start="14" data-byte-end="15" style="background-color:#fff59d;" title="value">1</mark>'
        in html
    )


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
