from collections.abc import Iterator

import pygit2 as git

from . import styling as s
from . import terminal
from .args import Args
from .common import connect, push_and_pr
from .error import GhitError
from .gitools import last_commits
from .stack import Stack


def _check_stack(
    repo: git.Repository, stack: Stack
) -> Iterator[tuple[Stack, int]]:
    if repo.is_empty:
        return
    depth = 0
    for record in stack.rtraverse(False):
        if record.depth < depth:
            break
        parent = record.get_parent()
        parent_ref = repo.references.get(f'refs/heads/{parent.branch_name}')
        record_ref = repo.references.get(f'refs/heads/{record.branch_name}')
        if not record_ref:
            continue
        a, _ = repo.ahead_behind(parent_ref.target, record_ref.target)
        if a != 0:
            yield (record, a)
            depth = record.depth


def check(args: Args) -> None:
    repo, stack, _ = connect(args)
    for notsync in _check_stack(repo, stack):
        record, a = notsync
        terminal.stdout(
            s.warning('🗶'),
            s.emphasis(record.get_parent().branch_name),
            s.warning('is ahead of'),
            s.emphasis(record.branch_name),
            s.warning('with:'),
        )
        parent_ref = repo.references.get(
            f'refs/heads/{record.get_parent().branch_name}'
        )

        for commit in last_commits(repo, parent_ref.target, a):
            terminal.stdout(
                s.inactive(
                    f'\t[{commit.short_id}] {commit.message.splitlines()[0]}'
                )
            )

        terminal.stdout(
            '  Run `git rebase -i '
            + record.get_parent().branch_name
            + ' '
            + record.branch_name
            + '`.'
        )

    if not notsync:
        terminal.stdout(s.good('🗸 The stack is in shape.'))
    else:
        raise GhitError(s.warning('The stack is not in shape.'))


def stack_submit(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return
    origin = repo.remotes['origin']
    if not origin:
        raise GhitError(s.warning('No origin found for the repository.'))

    for record in stack.traverse(False):
        push_and_pr(repo, gh, origin, record)
