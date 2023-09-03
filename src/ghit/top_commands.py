import os

import pygit2 as git

from .args import Args
from .common import BadResult, connect, stack_filename
from .gitools import checkout, get_current_branch
from .stack import Stack, open_stack
from .styling import (
    calm,
    deleted,
    normal,
    warning,
    with_style,
)
from .gh import GH
from .gh_formatting import format_info


def _parent_tab(record: Stack) -> str:
    return "  " if record.is_last_child() else "│ "


def _print_gh_info(
    verbose: bool,
    gh: GH,
    parent_prefix: list[str],
    record: Stack,
) -> int:
    error = 0
    info: list[str] = []
    for pr, stats in gh.pr_stats(record).items():
        if stats.unresolved or stats.change_requested:
            error = 1
        info.extend(list(format_info(gh, verbose, record, pr, stats)))

    if len(info) == 1:
        print(" " + info[0])
    else:
        print()
        for i in info:
            print(
                " ",
                *parent_prefix,
                "│   " if record.length() else "    ",
                i,
            )
    return error


def ls(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return

    error = 0

    checked_out = get_current_branch(repo).branch_name
    parent_prefix: list[str] = []

    for record in stack.traverse():
        parent_prefix = parent_prefix[: record.depth - 2]

        _print_line(
            repo, record.branch_name == checked_out, parent_prefix, record
        )

        if record.get_parent():
            parent_prefix.append(_parent_tab(record))

        if gh:
            error = max(
                error,
                _print_gh_info(args.verbose, gh, parent_prefix, record),
            )
        else:
            print()

    if error:
        raise BadResult("ls")


def _print_line(
    repo: git.Repository,
    current: bool,
    parent_prefix: list[str],
    record: Stack,
) -> None:
    line_color = calm if current else normal
    line = [line_color("⯈" if current else " "), *parent_prefix]

    behind = 0
    branch = repo.branches.get(record.branch_name)
    if record.get_parent():
        if branch:
            parent = repo.lookup_branch(record.get_parent().branch_name)
            if parent:
                behind, _ = repo.ahead_behind(
                    parent.target,
                    branch.target,
                )
            else:
                behind = 0

        g1 = "└" if record.is_last_child() else "├"
        g2 = "⭦" if behind else "─"
        line.append(g1 + g2)

    line.append(
        (deleted if not branch else warning if behind else line_color)(
            with_style(
                "bold",
                record.branch_name,
            )
            if current
            else record.branch_name
        )
    )

    if behind != 0:
        line.append(warning(f"({behind} behind)"))

    if branch:
        if branch.upstream:
            a, b = repo.ahead_behind(
                branch.target,
                branch.upstream.target,
            )
            if a or b:
                line.append(
                    with_style(
                        "dim",
                        "↕" if a and b else "↑" if a else "↓",
                    )
                )
        else:
            line.append(line_color("*"))

    print(*line, end="")


def _move(args: Args, command: str) -> None:
    repo, stack, _ = connect(args)
    current = get_current_branch(repo).branch_name
    i = stack.traverse()
    p = None
    for record in i:
        if record.branch_name == current:
            if command == "up":
                record = p
            else:
                try:
                    record = next(i)
                except StopIteration:
                    return
            break
        p = record

    if record:
        if record.branch_name != current:
            checkout(repo, record)
    else:
        return _jump(args, "top")
    return


def up(args: Args) -> None:
    return _move(args, "up")


def down(args: Args) -> None:
    return _move(args, "down")


def _jump(args: Args, command: str) -> None:
    repo, stack, _ = connect(args)
    if command == "top":
        try:
            record = next(stack.traverse())
        except StopIteration:
            return
    else:
        for record in stack.traverse():
            pass
    if record and record.branch_name != get_current_branch(repo).branch_name:
        checkout(repo, record)
    return


def top(args: Args) -> None:
    return _jump(args, "top")


def bottom(args: Args) -> None:
    return _jump(args, "bottom")


def init(args: Args) -> None:
    repo = git.Repository(args.repository)
    repopath = os.path.dirname(os.path.abspath(repo.path))
    filename = stack_filename(repo)
    stack = open_stack(args.stack or filename)
    if stack:
        return

    if os.path.commonpath(
        [filename, repopath]
    ) == repopath and not repo.path_is_ignored(filename):
        with open(os.path.join(repopath, ".gitignore"), "a") as gitignore:
            gitignore.write(os.path.basename(filename) + "\n")

    with open(filename, "w") as ghitstack:
        ghitstack.write(get_current_branch(repo).branch_name + "\n")
