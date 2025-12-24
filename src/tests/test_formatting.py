from ghit.formatting import (
    BranchState,
    LinePart,
    format_branch_line,
    parent_tab,
    render_line_plain,
)
from ghit.stack import Stack, parse


def make_state(
    record: Stack,
    exists: bool = True,
    behind: int = 0,
    upstream_status: str = '',
) -> BranchState:
    """Helper to create a BranchState without a real repo."""
    return BranchState(
        record=record,
        exists=exists,
        behind=behind,
        upstream_status=upstream_status,
    )


class TestParentTab:
    def test_last_child_returns_spaces(self):
        stack = parse(['main', '.feature'])
        feature = stack.find('feature')
        assert feature is not None
        assert parent_tab(feature) == '  '

    def test_not_last_child_returns_pipe(self):
        stack = parse(['main', '.feature1', '.feature2'])
        feature1 = stack.find('feature1')
        assert feature1 is not None
        assert parent_tab(feature1) == '│ '


class TestFormatBranchLine:
    def test_root_branch_normal(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main)

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  main'
        assert parts[0].text == '  '  # cursor indicator
        assert parts[0].style == 'normal'

    def test_root_branch_current(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main)

        parts = format_branch_line([], state, current=True)
        text = render_line_plain(parts)

        assert text == '⯈ main'
        assert parts[0].text == '⯈ '
        assert parts[0].style == 'current'

    def test_child_branch_with_tree_connector(self):
        stack = parse(['main', '.feature'])
        feature = stack.find('feature')
        state = make_state(feature)

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  └─feature'

    def test_child_branch_not_last(self):
        stack = parse(['main', '.feature1', '.feature2'])
        feature1 = stack.find('feature1')
        state = make_state(feature1)

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  ├─feature1'

    def test_branch_behind_parent(self):
        stack = parse(['main', '.feature'])
        feature = stack.find('feature')
        state = make_state(feature, behind=3)

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  └⭦feature (3 behind)'
        # Branch name should have warning style
        name_part = next(p for p in parts if p.text == 'feature')
        assert name_part.style == 'warning'

    def test_branch_deleted(self):
        stack = parse(['main', '.feature'])
        feature = stack.find('feature')
        state = make_state(feature, exists=False)

        parts = format_branch_line([], state)

        name_part = next(p for p in parts if p.text == 'feature')
        assert name_part.style == 'deleted'

    def test_upstream_no_remote(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main, upstream_status='*')

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  main *'

    def test_upstream_ahead(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main, upstream_status='↑')

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  main ↑'
        upstream_part = next(p for p in parts if '↑' in p.text)
        assert upstream_part.style == 'dim'

    def test_upstream_behind(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main, upstream_status='↓')

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  main ↓'

    def test_upstream_diverged(self):
        stack = parse(['main'])
        main = stack.find('main')
        state = make_state(main, upstream_status='↕')

        parts = format_branch_line([], state)
        text = render_line_plain(parts)

        assert text == '  main ↕'

    def test_with_parent_prefix(self):
        stack = parse(['main', '.feature', '..subfeature'])
        subfeature = stack.find('subfeature')
        state = make_state(subfeature)

        parts = format_branch_line(['│ '], state)
        text = render_line_plain(parts)

        assert text == '  │ └─subfeature'

    def test_deep_nesting(self):
        stack = parse(['main', '.a', '..b', '...c'])
        c = stack.find('c')
        state = make_state(c)

        parts = format_branch_line(['│ ', '│ '], state)
        text = render_line_plain(parts)

        assert text == '  │ │ └─c'


class TestRenderLinePlain:
    def test_concatenates_all_parts(self):
        parts = [
            LinePart('  ', 'normal'),
            LinePart('├─', 'normal'),
            LinePart('feature', 'warning'),
            LinePart(' (2 behind)', 'warning'),
        ]
        assert render_line_plain(parts) == '  ├─feature (2 behind)'

    def test_empty_parts(self):
        assert render_line_plain([]) == ''

    def test_ignores_styles(self):
        parts = [
            LinePart('a', 'deleted'),
            LinePart('b', 'warning'),
            LinePart('c', 'dim'),
            LinePart('d', 'current'),
        ]
        assert render_line_plain(parts) == 'abcd'

