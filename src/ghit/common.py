from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pygit2 as git

from . import gh_formatting as ghf
from . import gh_graphql as ghgql
from . import styling as s
from . import terminal
from .args import Args
from .error import GhitError
from .gh import GH, init_gh
from .gh_formatting import pr_number_with_style
from .gitools import MyRemoteCallback, get_current_branch, last_commits
from .stack import Stack, open_stack


@dataclass
class Context:
    """Holds the repository, stack, and optional GitHub connection."""
    repo: git.Repository
    stack: Stack
    gh: GH | None
    args: Args

    @property
    def is_empty(self) -> bool:
        return self.repo.is_empty

    @property
    def offline(self) -> bool:
        return self.args.offline

    @property
    def verbose(self) -> bool:
        return self.args.verbose


class ConnectionsCache:
    _context: Context | None = None


GHIT_STACK_DIR = '.ghit'
GHIT_STACK_FILENAME = 'stack'


def stack_filename(repo: git.Repository) -> Path:
    env = os.getenv('GHIT_STACK')
    return Path(env) if env else Path(repo.path).resolve().parent / GHIT_STACK_DIR / GHIT_STACK_FILENAME


def connect(args: Args) -> Context:
    if ConnectionsCache._context is not None:
        return ConnectionsCache._context
    repo = git.Repository(args.repository)
    if repo.is_empty:
        return Context(repo=repo, stack=Stack(), gh=None, args=args)
    stack = open_stack(Path(args.stack) if args.stack else stack_filename(repo))

    if not stack:
        if args.stack:
            raise GhitError(s.danger('No stack found in ' + args.stack))
        stack = Stack()
        current = get_current_branch(repo)
        if current is None or current.branch_name is None:
            raise GhitError(s.danger('No current branch found'))
        stack.add_child(current.branch_name)
    ConnectionsCache._context = Context(
        repo=repo,
        stack=stack,
        gh=init_gh(repo, stack, args.offline),
        args=args,
    )
    return ConnectionsCache._context


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
        s.emphasis(origin.url or '<empty>'),
        '.',
        sep='',
    )


def push_and_pr(
    ctx: Context,
    origin: git.Remote,
    record: Stack,
    title: str = '',
    draft: bool = False,
) -> tuple[list[ghgql.PR], bool]:
    if record.branch_name is None:
        raise GhitError(s.danger('Record has no branch name'))
    if not ctx.gh:
        raise GhitError(s.danger('No GitHub connection'))
    branch = ctx.repo.branches[record.branch_name]
    if not branch.upstream:
        push_branch(origin, branch)
        update_upstream(ctx.repo, origin, branch)

    prs = ctx.gh.get_prs(record.branch_name)
    for pr in prs:
        logging.debug('found pr: %d closed=%s merged=%s', pr.number, pr.closed, pr.merged)
    if prs:
        for pr in prs:
            if ctx.gh.update_dependencies(pr):
                terminal.stdout(f'Updated dependencies in {pr_number_with_style(pr)}.')

            if pr.closed or pr.merged:
                continue
            if ctx.gh.update_pr(record, pr):
                terminal.stdout(f'Set PR {pr_number_with_style(pr)} base branch to {s.emphasis(pr.base)}.')

    else:
        parent = record.get_parent()
        if parent is None or parent.branch_name is None:
            raise GhitError(s.danger('No parent branch to base PR on'))
        pr = ctx.gh.create_pr(parent.branch_name, record.branch_name, title, draft)
        terminal.stdout(
            'Created draft PR ' if draft else 'Created PR ',
            pr_number_with_style(pr),
            '.',
            sep='',
        )
        prs.append(pr)
        return prs, True
    return prs, False


def rewrite_stack(ctx: Context) -> None:
    filename = Path(ctx.args.stack) if ctx.args.stack else stack_filename(ctx.repo)
    with filename.open('w') as ghit_stack:
        ghit_stack.write('\n'.join(ctx.stack.dumps()) + '\n')


def has_finished_pr(ctx: Context, record: Stack) -> bool:
    if record.branch_name is None or not ctx.gh:
        return False
    prs = ctx.gh.get_prs(record.branch_name)
    all_finished = all(
        pr.state in ['CLOSED', 'MERGED'] and ctx.repo.lookup_branch(record.branch_name) for pr in prs
    )
    for pr in prs:
        if pr.state in ['CLOSED', 'MERGED'] and ctx.repo.lookup_branch(record.branch_name):
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
    return bool(prs) and all_finished


def check_record(ctx: Context, record: Stack) -> bool:
    if ctx.gh and has_finished_pr(ctx, record):
        return True
    parent = record.get_parent()
    if parent is None:
        return True
    if parent.branch_name is None:
        return True
    if record.branch_name is None:
        return True
    parent_name = parent.branch_name
    record_name = record.branch_name
    parent_ref = ctx.repo.references.get(f'refs/heads/{parent_name}')
    ref = ctx.repo.references.get(f'refs/heads/{record_name}')
    if not ref:
        return True
    if not parent_ref:
        return True
    a, b = ctx.repo.ahead_behind(parent_ref.target, ref.target)
    if not a:
        return True

    terminal.stdout(
        s.warning('🗶'),
        s.emphasis(parent.branch_name),
        s.warning('is ahead of'),
        s.emphasis(record_name),
        s.warning(f'with {a} commits:' if a != 1 else f'with {a} commit:'),
    )

    for commit in last_commits(ctx.repo, parent_ref.target, a):
        terminal.stdout(s.inactive(f'\t[{commit.short_id}] {commit.message.splitlines()[0]}'))

    if b:
        terminal.stdout(
            ' ',
            s.warning('while'),
            s.emphasis(record_name),
            s.warning((f'has {b} commits' if b != 1 else f'has {b} commit') + ' on top of'),
            s.emphasis(parent.branch_name) + s.warning(':'),
        )
        for commit in last_commits(ctx.repo, ref.target, b):
            terminal.stdout(s.inactive(f'\t[{commit.short_id}] {commit.message.splitlines()[0]}'))

    terminal.stdout(
        ' ',
        s.warning('Run `') + 'git rebase -i --onto',
        s.emphasis(parent.branch_name),
        s.emphasis(record_name) + s.warning(f'~{b}'),
        s.emphasis(record_name) + s.warning('`.'),
    )
    terminal.stdout()

    return False
