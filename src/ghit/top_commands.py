from .common import *
from .styling import *
from .args import Args


def ls(args: Args):
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return

    checked_out = get_current_branch(repo).branch_name
    parent_prefix: list[str] = []

    def parent_tab(record: Stack) -> str:
        return "  " if record.is_last_child() else "│ "

    for record in stack.traverse():
        parent_prefix = parent_prefix[: record.depth - 1]
        current = record.branch_name == checked_out

        line = _print_line(
            repo,
            current,
            parent_prefix,
            record,
        )

        if not record.first_level():
            parent_prefix.append(parent_tab(record))

        if gh:
            info = gh.pr_info(args, record)
            if len(info) == 1:
                line.append(info[0])
            elif len(info) > 1:
                print(" ".join(line))
                for i in info:
                    print(
                        " ",
                        " ".join(parent_prefix),
                        "│   " if record._children else "    ",
                        i,
                    )
                continue
        print(" ".join(line))


def _print_line(
    repo: git.Repository,
    current: bool,
    parent_prefix: list[str],
    record: Stack,

) -> list[str]:
    line_color = calm if current else normal
    line = [line_color("⯈" if current else " "), *parent_prefix]

    behind = 0
    branch = repo.branches.get(record.branch_name)
    if not record.first_level():
        if branch:
            behind, _ = repo.ahead_behind(
                repo.branches[record.get_parent().branch_name].target,
                branch.target,
            )

        g1 = "└" if record.is_last_child() else "├"
        g2 = "⭦" if behind else "─"
        line.append(g1 + g2)

    line.append(
        (deleted if not branch else warning if behind else line_color)(
            with_style("bold", record.branch_name) if current else record.branch_name
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
                line.append(with_style("dim", "↕" if a and b else "↑" if a else "↓"))
        else:
            line.append(line_color("*"))

    return line


def _move(args: Args, command: str):
    repo, stack, _ = connect(args)
    to_checkout_name = get_current_branch(repo).branch_name
    p = stack

    pick_next: bool = False
    prev_name: str | None = None
    for record in stack.traverse():
        p = record.get_parent()
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
        checkout(repo, p.branch_name, to_checkout_name)
    else:
        _jump(args, "top")


def up(args):
    _move(args, "up")


def down(args):
    _move(args, "down")


def _jump(args: Args, command: str):
    repo, stack, _ = connect(args)
    p = stack
    to_checkout_name: str | None = None
    for record in stack.traverse():
        p = record.get_parent()
        to_checkout_name = record.branch_name
        if command == "top":
            break
    if to_checkout_name is not None:
        checkout(repo, p.branch_name, to_checkout_name)


def top(args):
    _jump(args, "top")


def bottom(args):
    _jump(args, "bottom")
