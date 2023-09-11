import logging
import os
from pathlib import Path

import pygit2 as git

from . import styling as s
from . import terminal
from .__init__ import __version__
from .args import Args
from .common import GHIT_STACK_DIR, connect, stack_filename
from .error import GhitError
from .gh import GH
from .gh_formatting import format_info
from .gitools import checkout, get_current_branch
from .stack import Stack, open_stack


def _parent_tab(record: Stack) -> str:
    return '  ' if record.is_last_child() else '│ '


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
        terminal.stdout(' ' + info[0])
    else:
        terminal.stdout()
        for i in info:
            terminal.stdout(
                ' ',
                *parent_prefix,
                '│   ' if record.length() else '    ',
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
        parent_prefix = parent_prefix[: max(record.depth - 1, 0)]

        _print_line(repo, record.branch_name == checked_out, parent_prefix, record)

        if record.get_parent():
            parent_prefix.append(_parent_tab(record))

        if gh:
            error = max(
                error,
                _print_gh_info(args.verbose, gh, parent_prefix, record),
            )
        else:
            terminal.stdout()

    if error:
        raise GhitError


def _print_line(
    repo: git.Repository,
    current: bool,
    parent_prefix: list[str],
    record: Stack,
) -> None:
    line_color = s.calm if current else s.normal
    line = [line_color('⯈' if current else ' '), *parent_prefix]

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

        g1 = '└' if record.is_last_child() else '├'
        g2 = '⭦' if behind else '─'
        line.append(g1 + g2)

    line.append(
        (s.deleted if not branch else s.warning if behind else line_color)(
            s.with_style(
                'bold',
                record.branch_name,
            )
            if current
            else record.branch_name
        )
    )

    if behind != 0:
        line.append(s.warning(f'({behind} behind)'))

    if branch:
        if branch.upstream:
            a, b = repo.ahead_behind(
                branch.target,
                branch.upstream.target,
            )
            if a or b:
                line.append(
                    s.with_style(
                        'dim',
                        '↕' if a and b else '↑' if a else '↓',
                    )
                )
        else:
            line.append(line_color('*'))

    terminal.stdout(*line, end='')


def _move(args: Args, command: str) -> None:
    repo, stack, _ = connect(args)
    current = get_current_branch(repo).branch_name
    i = stack.traverse()
    p = None
    record = None
    for r in i:
        if r.branch_name == current:
            if command == 'up':
                record = p
            else:
                try:
                    record = next(i)
                except StopIteration:
                    return None
            break
        p = r

    if record:
        if record.branch_name != current:
            checkout(repo, record)
    else:
        return _jump(args, 'top')
    return None


def up(args: Args) -> None:
    return _move(args, 'up')


def down(args: Args) -> None:
    return _move(args, 'down')


def _jump(args: Args, command: str) -> None:
    repo, stack, _ = connect(args)
    record: Stack = None
    if command == 'top':
        try:
            record = next(stack.traverse())
        except StopIteration:
            return
    else:
        for r in stack.traverse():
            record = r
    if record and record.branch_name != get_current_branch(repo).branch_name:
        checkout(repo, record)
    return


def top(args: Args) -> None:
    return _jump(args, 'top')


def bottom(args: Args) -> None:
    return _jump(args, 'bottom')


def init(args: Args) -> None:
    if args.stack or os.getenv('GHIT_STACK'):
        raise GhitError
    repo = git.Repository(args.repository)
    repopath = Path(repo.workdir).resolve()
    filename = stack_filename(repo)
    logging.debug('stack filename: %s', filename)
    logging.debug('stack arg: %s', args.stack)

    stack = open_stack(Path(args.stack) if args.stack else filename)
    if stack:
        return
    logging.debug('%s vs %s', filename, repopath)
    if os.path.commonpath([filename, repopath]) == str(repopath):
        dotghit = Path(repopath / GHIT_STACK_DIR)
        logging.debug('creating dir %s', dotghit)

        dotghit.mkdir(exist_ok=True)
        if not repo.path_is_ignored(str(filename)):
            with (dotghit / '.gitignore').open('w') as gitignore:
                gitignore.write('*\n')

    with filename.open('w') as ghitstack:
        branch_name = repo.config['init.defaultBranch'] if repo.is_empty else get_current_branch(repo).branch_name
        ghitstack.write(branch_name + '\n')

def version(_: Args) -> None:
    terminal.stdout(__version__)
