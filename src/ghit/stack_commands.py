from .common import *
from .styling import *
from .gh import initGH

def ls(args: Args):
    repo, stack = connect(args)
    if repo.is_empty:
        return

    checked_out = get_current_branch(repo).branch_name
    parent_prefix: list[str] = []

    gh = initGH(repo, stack, args.offline)

    for record in stack.traverse():
        parent_prefix = parent_prefix[: record.depth - 1]
        current = record.branch_name == checked_out
        last_child = (
            record.index == record.parent.children - 1 if record.parent else False
        )

        line = _print_line(
            repo, current, parent_prefix, record.parent, record.branch_name, last_child
        )
        if gh:
            info = gh.pr_info(record.branch_name)
            if info:
                line.append(info)

        print(" ".join(line))
        if record.parent:
            parent_prefix.append(
                "  " if record.index == record.parent.children - 1 else "│ "
            )


def _print_line(
    repo: git.Repository,
    current: bool,
    parent_prefix: list[str],
    parent: StackRecord,
    branch_name: str,
    last_child: bool,
) -> list[str]:
    line_color = calm if current else normal
    line = [line_color("⯈" if current else " "), *parent_prefix]

    behind = 0
    branch = repo.branches.get(branch_name)
    if parent:
        if branch:
            behind, _ = repo.ahead_behind(
                repo.branches[parent.branch_name].target,
                branch.target,
            )

        g1 = "└" if last_child else "├"
        g2 = "⭦" if behind else "─"
        line.append(g1 + g2)

    line.append(
        (deleted if not branch else warning if behind else line_color)(
            with_style("bold", branch_name) if current else branch_name
        )
    )

    if behind != 0:
        line.append(warning(f"({behind} behind)"))

    if branch:
        if branch.upstream:
            a, b = repo.ahead_behind(
                branch.target,
                branch.upstream.target,
            )
            if a or b:
                line.append(
                    with_style("dim", "↕" if a and b else "↑" if a else "↓")
                )
        else:
            line.append(line_color("*"))

    return line


def _move(args: Args, command: str):
    repo, stack = connect(args)
    to_checkout_name = get_current_branch(repo).branch_name
    parent: StackRecord = None

    pick_next: bool = False
    prev_name: str | None = None
    for record in stack.traverse():
        parent = record.parent
        if pick_next:
            to_checkout_name = record.branch_name
            break
        if record.branch_name == to_checkout_name:
            if command == "up":
                to_checkout_name = prev_name
                break
            pick_next = True
        prev_name = record.branch_name
    if to_checkout_name is not None:
        checkout(repo, parent.branch_name, to_checkout_name)
    else:
        _jump(args, "top")


def up(args):
    _move(args, "up")


def down(args):
    _move(args, "down")


def _jump(args: Args, command: str):
    repo, stack = connect(args)
    parent: StackRecord = None
    to_checkout_name: str | None = None
    for record in stack.traverse():
        parent = record.parent
        to_checkout_name = record.branch_name
        if command == "top":
            break
    if to_checkout_name is not None:
        checkout(repo, parent.branch_name, to_checkout_name)


def top(args):
    _jump(args, "top")


def bottom(args):
    _jump(args, "bottom")


def restack(args: Args):
    repo, stack = connect(args)
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
            print(
                inactive(
                    f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"
                )
            )

        print(f"  Run `git rebase -i {parent.branch_name} {record.branch_name}`.")


def stack_sync(args: Args):
    repo, stack = connect(args)
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
