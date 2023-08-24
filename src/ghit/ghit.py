#!/usr/bin/env python3

import os
import argparse
import logging
import pygit2 as git
from dataclasses import dataclass

from .gitools import *
from .styling import *
from .stack import Stack, open_stack, StackRecord
from .gh import initGH


@dataclass
class Args:
    stack: str
    repository: str
    offline: bool
    title: str
    debug: bool


def connect(args: Args) -> tuple[git.Repository, Stack]:
    repo = git.Repository(args.repository)
    if repo.is_empty:
        return repo, None
    stack = open_stack(args.stack)
    if not stack:
        stack = Stack()
        current = get_current_branch(repo)
        stack.add_child([], current.branch_name)
    return repo, stack


# region commands


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
        checkout(repo, parent, to_checkout_name)
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
        checkout(repo, parent, to_checkout_name)


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


def pr_sync(args: Args):
    repo, stack = connect(args)
    if repo.is_empty:
        return

    gh = initGH(repo, stack, args.offline)
    if gh is None:
        return
    for record in stack.traverse():
        if record.parent is None:
            continue
        prs = gh.find_PRs(record.branch_name)
        if len(prs) == 0:
            gh.create_pr(record.parent.branch_name, record.branch_name)
        else:
            gh.comment(record.branch_name)


class MyRemoteCallback(git.RemoteCallbacks):
    refname: str | None
    message: str | None

    def push_update_reference(self, refname, message):
        self.message = message
        self.refname = refname

    def credentials(self, url, username_from_url, allowed_types):
        return get_git_ssh_credentials()


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


def update_upstream(repo: git.Repository, origin: git.Remote, branch: git.Branch):
    full_name = branch.resolve().name
    mrc = MyRemoteCallback()
    origin.push([full_name], callbacks=mrc)
    if not mrc.message:
        # TODO: weak logic?
        branch_ref: str = origin.get_refspec(0).transform(full_name)
        branch.upstream = repo.branches.remote[branch_ref.removeprefix("refs/remotes/")]
        print(
            "Pushed ",
            emphasis(branch.branch_name),
            " to remote ",
            emphasis(origin.url),
            " and set upstream to ",
            emphasis(branch.upstream.branch_name),
            ".",
            sep="",
        )


def update_pr(args: Args):
    repo, stack = connect(args)
    gh = initGH(repo, stack, args.offline)
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


# endregion commands


def ghit(argv: list[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--repository", default=".")
    parser.add_argument(
        "-s", "--stack", default=os.getenv("GHIT_STACK") or ".ghit.stack"
    )
    parser.add_argument("-o", "--offline", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")

    commands = parser.add_subparsers(required=True)

    commands.add_parser("ls", help="show the branches of stack with").set_defaults(
        func=ls
    )
    commands.add_parser("up", help="check out one branch up the stack").set_defaults(
        func=up
    )
    commands.add_parser(
        "down", help="check out one branch down the stack"
    ).set_defaults(func=down)
    commands.add_parser("top", help="check out the top of the stack").set_defaults(
        func=top
    )
    commands.add_parser(
        "bottom", help="check out the bottom of the stack"
    ).set_defaults(func=bottom)

    parser_stack = commands.add_parser("stack", aliases=["s", "st"])
    parser_stack_sub = parser_stack.add_subparsers()
    parser_stack_sub.add_parser(
        "restack",
        help="suggest git commands to rebase the branches according to the stack",
    ).set_defaults(func=restack)
    parser_stack_sub.add_parser(
        "sync", help="fetch from origin and push stack branches upstream"
    ).set_defaults(func=stack_sync)

    parser_pr = commands.add_parser("pr")
    parser_pr_sub = parser_pr.add_subparsers()
    upr = parser_pr_sub.add_parser(
        "update",
        help="create new draft PR or update the existing PR opened from the current branch",
    )
    upr.add_argument("-t", "--title", help="PR title")
    upr.set_defaults(func=update_pr)
    parser_pr_sub.add_parser(
        "sync", help="creates or updates PRs of the stack"
    ).set_defaults(func=pr_sync)

    args = parser.parse_args(args=argv)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.debug:
        args.func(args)
    else:
        try:
            args.func(args)
        except Exception as e:
            print("Error:", e)
