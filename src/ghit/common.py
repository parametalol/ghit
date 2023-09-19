import logging
import os
from pathlib import Path

import pygit2 as git

from . import gh_formatting as ghf
from . import styling as s
from . import terminal
from .args import Args
from .error import GhitError
from .gh import GH, init_gh
from .gh_formatting import pr_number_with_style
from .gitools import MyRemoteCallback, get_current_branch, last_commits
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
    for pr in prs:
        logging.debug('found pr: %d closed=%s merged=%s', pr.number, pr.closed, pr.merged)
    if prs:
        for pr in prs:
            commented = gh.comment(pr)
            if commented:
                terminal.stdout(f'Commented {pr_number_with_style(pr)}.')
            elif commented is not None:
                terminal.stdout(f'Updated comment in {pr_number_with_style(pr)}.')

            if pr.closed or pr.merged:
                continue
            if gh.update_pr(record, pr):
                terminal.stdout(f'Set PR {pr_number_with_style(pr)} base branch to {s.emphasis(pr.base)}.')

    else:
        pr = gh.create_pr(record.get_parent().branch_name, record.branch_name, title, draft)
        terminal.stdout(
            'Created draft PR ' if draft else 'Created PR ',
            pr_number_with_style(pr),
            '.',
            sep='',
        )


def rewrite_stack(args_stack: str, repo: git.Repository, stack: Stack):
    with (Path(args_stack) if args_stack else stack_filename(repo)).open('w') as ghit_stack:
        ghit_stack.write('\n'.join(stack.dumps()) + '\n')


def has_finished_pr(repo: git.Repository, gh: GH, record: Stack):
    prs = gh.get_prs(record.branch_name)
    all_finished = all(pr.state in ['CLOSED', 'MERGED'] and repo.lookup_branch(record.branch_name) for pr in prs)
    for pr in prs:
        if pr.state in ['CLOSED', 'MERGED'] and repo.lookup_branch(record.branch_name):
            terminal.stdout(
                s.good('🗸 Found PR'),
                ghf.pr_number_with_style(pr),
                s.good('with head'),
                s.emphasis(record.branch_name) + s.good('.'),
            )
            terminal.stdout(
                ' ',
                s.good('You may delete local branch with `') + 'git branch --delete',
                s.emphasis(record.branch_name) + s.good('`.'),
            )
            terminal.stdout()
            break
    return prs and all_finished


def check_record(repo: git.Repository, gh: GH, record: Stack) -> bool:
    if gh and has_finished_pr(repo, gh, record):
        return True
    parent = record.get_parent()
    if parent is None:
        return True
    parent_ref = repo.references.get(f'refs/heads/{parent.branch_name}')
    ref = repo.references.get(f'refs/heads/{record.branch_name}')
    if not ref:
        return True
    a, b = repo.ahead_behind(parent_ref.target, ref.target)
    if not a:
        return True

    terminal.stdout(
        s.warning('🗶'),
        s.emphasis(record.get_parent().branch_name),
        s.warning('is ahead of'),
        s.emphasis(record.branch_name),
        s.warning(f'with {a} commits:' if a != 1 else f'with {a} commit:'),
    )

    for commit in last_commits(repo, parent_ref.target, a):
        terminal.stdout(s.inactive(f'\t[{commit.short_id}] {commit.message.splitlines()[0]}'))

    if b:
        terminal.stdout(
            ' ',
            s.warning('while'),
            s.emphasis(record.branch_name),
            s.warning((f'has {b} commits' if b != 1 else f'has {b} commit') + ' on top of'),
            s.emphasis(record.get_parent().branch_name) + s.warning(':'),
        )
        for commit in last_commits(repo, ref.target, b):
            terminal.stdout(s.inactive(f'\t[{commit.short_id}] {commit.message.splitlines()[0]}'))

    terminal.stdout(
        ' ',
        s.warning('Run `') + 'git rebase -i --onto',
        s.emphasis(record.get_parent().branch_name),
        s.emphasis(record.branch_name) + s.warning(f'~{b}'),
        s.emphasis(record.branch_name) + s.warning('`.'),
    )
    terminal.stdout()

    return False
