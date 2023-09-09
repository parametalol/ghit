from . import styling as s
from .common import (
    Args,
    check_record,
    connect,
    push_and_pr,
    rewrite_stack,
)
from .error import GhitError
from .gitools import checkout, get_current_branch


def branch_submit(args: Args) -> None:
    repo, stack, gh = connect(args)
    if not gh:
        return
    origin = repo.remotes['origin']
    if not origin:
        raise GhitError(s.danger('No origin found for the repository.'))
    current = get_current_branch(repo)
    for record in stack.traverse():
        if record.branch_name == current.branch_name:
            push_and_pr(repo, gh, origin, record, args.title, args.draft)
            break
    else:
        raise GhitError(
            s.danger("Couldn't find current branch in the stack."),
        )
    return


def create(args: Args) -> None:
    repo, stack, _ = connect(args)

    branch = repo.lookup_branch(args.branch)
    if branch:
        raise GhitError(
            s.danger('Branch ') + s.emphasis(args.branch) + s.danger(' already exists.'),
        )

    current = get_current_branch(repo)
    parent = None
    for record in stack.traverse(True):
        if record.branch_name == current.branch_name:
            parent = record
            break
    else:
        parent = stack.add_child(current.branch_name)

    branch = repo.branches.local.create(name=args.branch, commit=repo.get(repo.head.target))

    new_record = parent.add_child(args.branch)
    checkout(repo, new_record)

    rewrite_stack(args.stack, repo, stack)


def check(args: Args) -> None:
    repo, stack, gh = connect(args)
    if not check_record(repo, gh, stack):
        raise GhitError
