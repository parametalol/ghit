import os
from pathlib import Path

import pygit2 as git

from . import styling as s
from . import terminal
from .args import Args
from .error import GhitError
from .gh import GH, init_gh
from .gh_formatting import pr_number_with_style
from .gitools import MyRemoteCallback, get_current_branch
from .stack import Stack, open_stack


class ConnectionsCache:
    _connections: tuple[git.Repository, Stack, GH] = None


GHIT_STACK_DIR = '.ghit'
GHIT_STACK_FILENAME = 'stack'


def stack_filename(repo: git.Repository) -> Path:
    env = os.getenv('GHIT_STACK')
    return Path(env) if env else Path(repo.path).resolve().parent / GHIT_STACK_DIR / GHIT_STACK_FILENAME


def connect(args: Args) -> tuple[git.Repository, Stack, GH]:
    if ConnectionsCache._connections:
        return ConnectionsCache._connections
    repo = git.Repository(args.repository)
    if repo.is_empty:
        return repo, Stack(), None
    stack = open_stack(Path(args.stack) if args.stack else stack_filename(repo))

    if not stack:
        if args.stack:
            raise GhitError(s.danger('No stack found in ' + args.stack))
        stack = Stack()
        current = get_current_branch(repo)
        stack.add_child(current.branch_name)
    ConnectionsCache._connections = (repo, stack, init_gh(repo, stack, args.offline))
    return ConnectionsCache._connections


def update_upstream(repo: git.Repository, origin: git.Remote, branch: git.Branch):
    # TODO: weak logic?
    branch_ref: str = origin.get_refspec(0).transform(branch.resolve().name)
    branch.upstream = repo.branches.remote[branch_ref.removeprefix('refs/remotes/')]
    terminal.stdout(
        'Set upstream to ',
        s.emphasis(branch.upstream.branch_name),
        '.',
        sep='',
    )


def push_branch(origin: git.Remote, branch: git.Branch):
    mrc = MyRemoteCallback()
    origin.push([branch.name], callbacks=mrc)
    if mrc.message:
        raise GhitError(
            s.danger('Failed to push ') + s.emphasis(branch.name) + s.danger(': ' + mrc.message),
        )

    terminal.stdout(
        'Pushed ',
        s.emphasis(branch.branch_name),
        ' to remote ',
        s.emphasis(origin.url),
        '.',
        sep='',
    )


def push_and_pr(
    repo: git.Repository,
    gh: GH,
    origin: git.Remote,
    record: Stack,
    title: str = '',
    draft: bool = False,
) -> None:
    branch = repo.branches[record.branch_name]
    if not branch.upstream:
        push_branch(origin, branch)
        update_upstream(repo, origin, branch)

    prs = gh.get_prs(record.branch_name)
    if prs and not all(p.closed for p in prs):
        for pr in prs:
            if gh.comment(pr):
                terminal.stdout(f'Commented {pr_number_with_style(pr)}.')
            else:
                terminal.stdout(f'Updated comment in {pr_number_with_style(pr)}.')

            gh.update_pr(record, pr)
            terminal.stdout(f'Set PR {pr_number_with_style(pr)} base branch to {s.emphasis(pr.base)}.')
            terminal.stdout(s.colorful(pr.url))

    else:
        pr = gh.create_pr(record.get_parent().branch_name, record.branch_name, title, draft)
        terminal.stdout(
            'Created draft PR ' if draft else 'Created PR ',
            pr_number_with_style(pr),
            '.',
            sep='',
        )
        terminal.stdout(s.colorful(pr.url))
