"""Branch line formatting and rendering utilities.

This module provides structured formatting for branch lines in the stack,
with multiple rendering backends (ANSI terminal, plain text, curses).
"""

from dataclasses import dataclass

import pygit2 as git

from . import styling as s
from .stack import Stack


@dataclass
class BranchState:
    """Computed state for a branch in the stack."""

    record: Stack
    exists: bool
    behind: int
    upstream_status: str  # '', '↕', '↑', '↓', '*'


@dataclass
class LinePart:
    """A styled part of a branch line."""

    text: str
    style: str  # 'normal', 'current', 'warning', 'deleted', 'dim'


def parent_tab(record: Stack) -> str:
    """Return the tree prefix character for a record's children."""
    return '  ' if record.is_last_child() else '│ '


def compute_branch_state(repo: git.Repository, record: Stack) -> BranchState:
    """Compute the state of a branch relative to its parent and upstream."""
    branch = repo.branches.get(record.branch_name)
    behind = 0
    upstream_status = ''

    if record.get_parent() and branch:
        parent = repo.lookup_branch(record.get_parent().branch_name)
        if parent:
            behind, _ = repo.ahead_behind(parent.target, branch.target)

    if branch:
        if branch.upstream:
            a, b = repo.ahead_behind(branch.target, branch.upstream.target)
            if a or b:
                upstream_status = '↕' if a and b else '↑' if a else '↓'
        else:
            upstream_status = '*'

    return BranchState(
        record=record,
        exists=branch is not None,
        behind=behind,
        upstream_status=upstream_status,
    )


def format_branch_line(
    parent_prefix: list[str],
    state: BranchState,
    current: bool = False,
) -> list[LinePart]:
    """Format a branch line as structured parts with style hints."""
    record = state.record
    base_style = 'current' if current else 'normal'
    parts: list[LinePart] = []

    # Cursor indicator
    parts.append(LinePart('⯈ ' if current else '  ', base_style))

    # Parent prefix (tree lines from ancestors)
    if parent_prefix:
        parts.append(LinePart(''.join(parent_prefix), base_style))

    # Tree connector
    if record.get_parent():
        if record.is_in_stack():
            g1 = '└' if record.is_last_child() else '├'
            g2 = '⭦' if state.behind else '─'
        else:
            g1 = '╵' if record.is_last_child() else '┆'
            g2 = '⭦' if state.behind else '┄'
        parts.append(LinePart(g1 + g2, base_style))

    # Branch name
    name_style = 'deleted' if not state.exists else 'warning' if state.behind else base_style
    parts.append(LinePart(record.branch_name or '', name_style))

    # Behind indicator
    if state.behind:
        parts.append(LinePart(f' ({state.behind} behind)', 'warning'))

    # Upstream status
    if state.upstream_status:
        upstream_style = base_style if state.upstream_status == '*' else 'dim'
        parts.append(LinePart(' ' + state.upstream_status, upstream_style))

    return parts


def render_line_plain(parts: list[LinePart]) -> str:
    """Render line parts as plain text (no styling)."""
    return ''.join(p.text for p in parts)


def render_line_ansi(parts: list[LinePart], current: bool = False) -> str:
    """Render line parts with ANSI color codes."""
    line_color = s.calm if current else s.normal
    result = []

    for part in parts:
        match part.style:
            case 'deleted':
                result.append(s.deleted(part.text))
            case 'warning':
                result.append(s.warning(part.text))
            case 'dim':
                result.append(s.with_style('dim', part.text))
            case 'current':
                # Current branch: bold name, calm color for rest
                if part.text and not part.text.isspace() and '─' not in part.text:
                    result.append(s.calm(s.with_style('bold', part.text)))
                else:
                    result.append(s.calm(part.text))
            case _:
                result.append(line_color(part.text))

    return ''.join(result)

