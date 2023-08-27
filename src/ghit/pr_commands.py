from .common import *


def update_pr(args: Args):
    repo, stack, gh = connect(args)
    if gh is None:
        return
    origin = repo.remotes["origin"]
    if not origin:
        print(warning("No origin found for the repository."))
        return
    current = get_current_branch(repo)
    for record in stack.traverse():
        if record.branch_name == current.branch_name:
            sync_branch(args, repo, gh, origin, record)
            break
    else:
        print(warning("Couldn't find current branch in the stack."))
