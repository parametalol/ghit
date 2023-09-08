import pygit2 as git

from . import gh, terminal
from . import gh_formatting as ghf
from . import styling as s
from .args import Args
from .common import connect, push_and_pr
from .error import GhitError
from .gitools import last_commits
from .stack import Stack


def has_finished_pr(repo: git.Repository, gh: gh.GH, record: Stack):
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


def check(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return

    insync = True
    for record in stack.traverse(False):
        if gh and has_finished_pr(repo, gh, record):
            continue
        parent = record.get_parent()
        parent_ref = repo.references.get(f'refs/heads/{parent.branch_name}')
        ref = repo.references.get(f'refs/heads/{record.branch_name}')
        if not ref:
            continue
        a, b = repo.ahead_behind(parent_ref.target, ref.target)
        if not a:
            continue
        insync = False
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

    if not insync:
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
