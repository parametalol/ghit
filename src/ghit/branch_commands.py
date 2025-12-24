import pygit2 as git

from . import styling as s
from .args import Args
from .common import (
    check_record,
    connect,
    push_and_pr,
    rewrite_stack,
)
from .error import GhitError
from .gitools import checkout, get_current_branch


def branch_submit(args: Args) -> None:
    ctx = connect(args)
    if not ctx.gh:
        return
    origin = ctx.repo.remotes['origin']
    if not origin:
        raise GhitError(s.danger('No origin found for the repository.'))
    current = get_current_branch(ctx.repo)
    for record in ctx.stack.traverse():
        if record.branch_name == current.branch_name:
            push_and_pr(ctx, origin, record, args.title, args.draft)
            break
    else:
        raise GhitError(
            s.danger("Couldn't find current branch in the stack."),
        )
    return


def create(args: Args) -> None:
    ctx = connect(args)

    branch = ctx.repo.lookup_branch(args.branch)
    if branch:
        raise GhitError(
            s.danger('Branch ') + s.emphasis(args.branch) + s.danger(' already exists.'),
        )

    current = get_current_branch(ctx.repo)
    parent = None
    for record in ctx.stack.traverse(True):
        if record.branch_name == current.branch_name:
            parent = record
            break
    else:
        parent = ctx.stack.add_child(current.branch_name)

    head = ctx.repo.get(ctx.repo.head.target)
    if head is None or not isinstance(head, git.Commit):
        raise GhitError(s.danger('HEAD is not a Commit'))
    branch = ctx.repo.branches.local.create(name=args.branch, commit=head)

    new_record = parent.add_child(args.branch)
    checkout(ctx.repo, new_record)

    rewrite_stack(ctx)


def check(args: Args) -> None:
    ctx = connect(args)
    if not check_record(ctx, ctx.stack):
        raise GhitError
