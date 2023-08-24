from .common import *
from .gh import initGH

def pr_sync(args: Args):
    repo, stack, gh = connect(args)
    if repo.is_empty or not gh:
        return
    for record in stack.traverse():
        if record.parent is None:
            continue
        prs = gh.find_PRs(record.branch_name)
        if len(prs) == 0:
            gh.create_pr(record.parent.branch_name, record.branch_name)
        else:
            gh.comment(record.branch_name)


def update_pr(args: Args):
    repo, stack, gh = connect(args)
    if gh is None:
        return
    origin = repo.remotes["origin"]
    if not origin:
        return
    current = get_current_branch(repo)
    for record in stack.traverse():
        if record.branch_name != current.branch_name:
            continue
        branch = repo.branches[record.branch_name]
        if not branch.upstream:
            update_upstream(repo, origin, branch)
        prs = gh.find_PRs(record.branch_name)
        if len(prs) == 0:
            gh.create_pr(record.parent.branch_name, record.branch_name, args.title)
        else:
            gh.comment(record.branch_name)
        break
    else:
        print(warning("Couldn't find current branch in the stack."))
