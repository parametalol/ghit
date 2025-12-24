import logging
import os
from pathlib import Path

import pygit2 as git

from . import formatting as fmt
from . import terminal
from .__init__ import __version__
from .args import Args
from .common import GHIT_STACK_DIR, connect, stack_filename
from .error import GhitError
from .gh import GH
from .gh_formatting import format_info
from .gitools import checkout, get_current_branch, insert
from .stack import Stack, open_stack


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
    ctx = connect(args)
    if ctx.is_empty:
        return

    error = 0

    checked_out = get_current_branch(ctx.repo).branch_name
    parent_prefix: list[str] = []

    if not ctx.stack.find(checked_out):
        insert(ctx.repo, checked_out, ctx.stack)

    for record in ctx.stack.traverse():
        parent_prefix = parent_prefix[: max(record.depth - 1, 0)]

        _print_line(ctx.repo, record.branch_name == checked_out, parent_prefix, record)

        if record.get_parent():
            parent_prefix.append(fmt.parent_tab(record))

        if ctx.gh:
            error = max(
                error,
                _print_gh_info(ctx.verbose, ctx.gh, parent_prefix, record),
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
    """Print a branch line with ANSI colors."""
    state = fmt.compute_branch_state(repo, record)
    parts = fmt.format_branch_line(parent_prefix, state, current)
    terminal.stdout(fmt.render_line_ansi(parts, current), end='')


def _move(args: Args, command: str) -> None:
    ctx = connect(args)
    current = get_current_branch(ctx.repo).branch_name

    if not ctx.stack.find(current):
        insert(ctx.repo, current, ctx.stack)

    i = ctx.stack.traverse()
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
            checkout(ctx.repo, record)
    else:
        return _jump(args, 'top')
    return None


def up(args: Args) -> None:
    return _move(args, 'up')


def down(args: Args) -> None:
    return _move(args, 'down')


def _jump(args: Args, command: str) -> None:
    ctx = connect(args)
    record: Stack = None
    if command == 'top':
        try:
            record = next(ctx.stack.traverse())
        except StopIteration:
            return
    else:
        for r in ctx.stack.traverse():
            record = r
    if record and record.branch_name != get_current_branch(ctx.repo).branch_name:
        checkout(ctx.repo, record)
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
