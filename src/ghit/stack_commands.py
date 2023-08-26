from .common import *
from .styling import *
import pygit2 as git


def _check_stack(
    repo: git.Repository, stack: Stack
) -> Iterator[tuple[StackRecord, StackRecord, int]]:
    if repo.is_empty:
        return
    depth = 0
    for record in stack.rtraverse():
        if record.depth < depth:
            break
        parent = record.parent
        if parent is None:
            continue
        parent_ref = repo.references.get(f"refs/heads/{parent.branch_name}")
        record_ref = repo.references.get(f"refs/heads/{record.branch_name}")
        if not record_ref:
            continue
        a, _ = repo.ahead_behind(parent_ref.target, record_ref.target)
        if a != 0:
            yield (parent, record, a)
            depth = record.depth


def check(args: Args):
    repo, stack, _ = connect(args)
    for notsync in _check_stack(repo, stack):
        parent, record, a = notsync
        print(
            warning("🗶"),
            emphasis(parent.branch_name),
            warning("is ahead of"),
            emphasis(record.branch_name),
            warning("with:"),
        )
        parent_ref = repo.references.get(f"refs/heads/{parent.branch_name}")

        for commit in last_commits(repo, parent_ref.target, a):
            print(inactive(f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"))

        print(f"  Run `git rebase -i {parent.branch_name} {record.branch_name}`.")

    if not notsync:
        print(good("🗸 The stack is in shape."))


def restack(args: Args):
    repo, stack, _ = connect(args)

    for _ in _check_stack(repo, stack):
        return

    for record in stack.traverse():
        parent = record.parent
        if parent is None:
            continue
        parent_ref = repo.references.get(f"refs/heads/{parent.branch_name}")
        if parent_ref is None:
            continue
        record_ref = repo.references.get(f"refs/heads/{record.branch_name}")
        if record_ref is None:
            print(
                warning("No local branch"),
                emphasis(record.branch_name),
                warning("found"),
            )
            continue
        a, _ = repo.ahead_behind(parent_ref.target, record_ref.target)
        if a == 0:
            print(
                good("🗸"),
                emphasis(record.branch_name),
                good("is already on"),
                emphasis(parent.branch_name),
            )
            continue

        print()
        print(
            warning("🗶"),
            emphasis(parent.branch_name),
            warning("is ahead of"),
            emphasis(record.branch_name),
            warning("with:"),
        )

        for commit in last_commits(repo, parent_ref.target, a):
            print(inactive(f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"))

        print(f"  Run `git rebase -i {parent.branch_name} {record.branch_name}`.")


def stack_sync(args: Args):
    repo, stack, _ = connect(args)
    if repo.is_empty:
        return
    origin = repo.remotes["origin"]
    if not origin:
        return

    mrc = MyRemoteCallback()
    print("Fetching from", origin.url)
    progress = origin.fetch(callbacks=mrc)
    print("\treceived objects:", progress.received_objects)
    print("\ttotal deltas:", progress.total_deltas)
    print("\ttotal objects:", progress.total_objects)

    for record in stack.traverse():
        if record.parent is None:
            continue
        branch = repo.branches[record.branch_name]
        if not branch.upstream:
            update_upstream(repo, origin, branch)

def get_comments(args: Args):
    repo, stack, gh = connect(args)
    if repo.is_empty or not gh:
        return
    for pr_c in gh.get_pr_comments():
        pass

    for code_c in gh.get_code_comments():
        print(code_c['user']['login'], "@", code_c['updated_at'])
        print(code_c['path'])
        for line in str(code_c['body']).splitlines():
            print("\t", line)
        print()
