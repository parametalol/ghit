from .common import *


def branch_sync(args: Args) -> None:
    repo, stack, gh = connect(args)
    if not gh:
        return
    origin = repo.remotes["origin"]
    if not origin:
        raise BadResult("branch_sync", warning("No origin found for the repository."))
    current = get_current_branch(repo)
    for record in stack.traverse():
        if record.branch_name == current.branch_name:
            sync_branch(repo, gh, origin, record, args.title, args.draft)
            break
    else:
        raise BadResult(
            "branch_sync", warning("Couldn't find current branch in the stack.")
        )
    return
