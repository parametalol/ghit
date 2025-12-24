"""Inline interactive stack navigation."""

import sys
import termios
import tty

from . import formatting as fmt
from . import styling as s
from . import terminal
from .args import Args
from .common import Context, connect
from .gitools import checkout, get_current_branch, insert

# ANSI escape codes
_ESC = '\033'
_CLEAR_LINE = f'{_ESC}[K'
_HIDE_CURSOR = f'{_ESC}[?25l'
_SHOW_CURSOR = f'{_ESC}[?25h'


def _move_up(n: int) -> str:
    """ANSI escape to move cursor up n lines."""
    return f'{_ESC}[{n}A' if n > 0 else ''


def _getch() -> str:
    """Read a single character from stdin without echo."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Handle escape sequences (arrow keys)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                return f'\x1b[{ch3}'
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _render_line(parts: list[fmt.LinePart], is_selected: bool) -> str:
    """Render a line with ANSI colors, replacing cursor with selection indicator."""
    result = []

    # Selection indicator
    prefix = '→ ' if is_selected else '  '
    if is_selected:
        result.append(s.calm(s.with_style('bold', prefix)))
    else:
        result.append(prefix)

    # Render remaining parts (skip original cursor part)
    for part in parts[1:]:
        match part.style:
            case 'deleted':
                result.append(s.deleted(part.text))
            case 'warning':
                result.append(s.warning(part.text))
            case 'dim':
                result.append(s.with_style('dim', part.text))
            case 'current' if is_selected:
                if part.text and not part.text.isspace() and '─' not in part.text:
                    result.append(s.calm(s.with_style('bold', part.text)))
                else:
                    result.append(s.calm(part.text))
            case _:
                if is_selected:
                    result.append(s.calm(part.text))
                else:
                    result.append(part.text)

    return ''.join(result)


def _collect_stack_lines(ctx: Context) -> list[tuple[fmt.BranchState, list[fmt.LinePart]]]:
    """Collect all stack records with their formatted line parts."""
    lines: list[tuple[fmt.BranchState, list[fmt.LinePart]]] = []
    parent_prefix: list[str] = []

    for record in ctx.stack.traverse():
        parent_prefix = parent_prefix[: max(record.depth - 1, 0)]
        state = fmt.compute_branch_state(ctx.repo, record)
        parts = fmt.format_branch_line(parent_prefix, state)
        lines.append((state, parts))
        if record.get_parent():
            parent_prefix.append(fmt.parent_tab(record))

    return lines


def _render_menu(lines: list[tuple[fmt.BranchState, list[fmt.LinePart]]], selected: int) -> None:
    """Render the entire menu."""
    for i, (_state, parts) in enumerate(lines):
        line = _render_line(parts, i == selected)
        print(f'{_CLEAR_LINE}{line}', flush=True)  # noqa: T201


def _run_navigate(lines: list[tuple[fmt.BranchState, list[fmt.LinePart]]], current_idx: int) -> fmt.BranchState | None:
    """Run the inline interactive selection loop."""
    selected = current_idx
    num_lines = len(lines)

    # Initial render
    print(_HIDE_CURSOR, end='', flush=True)  # noqa: T201
    try:
        _render_menu(lines, selected)

        while True:
            key = _getch()

            new_selected = selected
            if key in ('\x1b[A', 'k') and selected > 0:  # Up arrow or vim k
                new_selected = selected - 1
            elif key in ('\x1b[B', 'j') and selected < num_lines - 1:  # Down arrow or vim j
                new_selected = selected + 1
            elif key in ('\r', '\n'):  # Enter
                return lines[selected][0]
            elif key in ('q', '\x1b', '\x03'):  # q, Escape, or Ctrl+C
                return None

            if new_selected != selected:
                # Move back up and redraw
                print(_move_up(num_lines), end='', flush=True)  # noqa: T201
                selected = new_selected
                _render_menu(lines, selected)

    finally:
        print(_SHOW_CURSOR, end='', flush=True)  # noqa: T201


def navigate(args: Args) -> None:
    """Interactive stack navigation."""
    ctx = connect(args)
    if ctx.is_empty:
        return

    checked_out = get_current_branch(ctx.repo).branch_name

    if not ctx.stack.find(checked_out):
        insert(ctx.repo, checked_out, ctx.stack)

    lines = _collect_stack_lines(ctx)
    if not lines:
        return

    # Find current branch index
    current_idx = next(
        (i for i, (state, _) in enumerate(lines) if state.record.branch_name == checked_out),
        0,
    )

    # Run inline interactive mode
    result = _run_navigate(lines, current_idx)

    if result and result.record.branch_name != checked_out:
        checkout(ctx.repo, result.record)
        terminal.stdout(f'Switched to {s.emphasis(result.record.branch_name)}')
