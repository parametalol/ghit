from .common import (
    Args,
    connect,
    BadResult,
    push_and_pr,
    stack_filename,
)
from .styling import emphasis, danger
from .gitools import get_current_branch, checkout


def branch_submit(args: Args) -> None:
    repo, stack, gh = connect(args)
    if not gh:
        return
    origin = repo.remotes["origin"]
    if not origin:
        raise BadResult(
            "branch_submit", danger("No origin found for the repository.")
        )
    current = get_current_branch(repo)
    for record in stack.traverse():
        if record.branch_name == current.branch_name:
            push_and_pr(repo, gh, origin, record, args.title, args.draft)
            break
    else:
        raise BadResult(
            "branch_submit",
            danger("Couldn't find current branch in the stack."),
        )
    return


def create(args: Args) -> None:
    repo, stack, _ = connect(args)
    current = get_current_branch(repo)
    for record in stack.traverse(True):
        if record.branch_name == current.branch_name:
            break
    else:
        record = stack.add_child(current.branch_name)
    record = record.add_child(args.branch)

    branch = repo.lookup_branch(args.branch)
    if branch:
        raise BadResult(
            "create",
            danger("Branch ")
            + emphasis(args.branch)
            + danger(" already exists."),
        )
    branch = repo.branches.local.create(
        name=args.branch, commit=repo.get(repo.head.target)
    )

    checkout(repo, record)

    lines = []
    stack.dumps(lines)
    with open(args.stack or stack_filename(repo), "w") as ghit_stack:
        ghit_stack.write("\n".join(lines) + "\n")
