import pygit2 as git
import os
from .stack import Stack, open_stack
from .gitools import get_current_branch, MyRemoteCallback
from .styling import emphasis, warning, danger
from .gh import initGH, GH
from .gh_formatting import pr_number_with_style
from .args import Args

__connections: tuple[git.Repository, Stack, GH] = None

GHIT_STACK_FILENAME = ".ghit.stack"


def stack_filename(repo: git.Repository) -> str:
    repopath = os.path.dirname(os.path.abspath(repo.path))
    return os.path.join(repopath, GHIT_STACK_FILENAME)


def connect(args: Args) -> tuple[git.Repository, Stack, GH]:
    global __connections
    if __connections:
        return __connections
    repo = git.Repository(args.repository)
    if repo.is_empty:
        return repo, Stack(), None
    stack = open_stack(args.stack or stack_filename(repo))

    if not stack:
        if args.stack:
            raise BadResult(
                "connect", danger("No stack found in " + args.stack)
            )
        stack = Stack()
        current = get_current_branch(repo)
        stack.add_child(current.branch_name)
    __connections = (repo, stack, initGH(repo, stack, args.offline))
    return __connections


def update_upstream(
    repo: git.Repository, origin: git.Remote, branch: git.Branch
):
    # TODO: weak logic?
    branch_ref: str = origin.get_refspec(0).transform(branch.resolve().name)
    branch.upstream = repo.branches.remote[
        branch_ref.removeprefix("refs/remotes/")
    ]
    print(
        "Set upstream to ",
        emphasis(branch.upstream.branch_name),
        ".",
        sep="",
    )


def push_branch(origin: git.Remote, branch: git.Branch):
    mrc = MyRemoteCallback()
    origin.push([branch.name], callbacks=mrc)
    if mrc.message:
        raise BadResult(
            "Push branch",
            danger("Failed to push ")
            + emphasis(branch.name)
            + danger(": " + mrc.message),
        )

    print(
        "Pushed ",
        emphasis(branch.branch_name),
        " to remote ",
        emphasis(origin.url),
        ".",
        sep="",
    )


def push_and_pr(
    repo: git.Repository,
    gh: GH,
    origin: git.Remote,
    record: Stack,
    title: str = "",
    draft: bool = False,
) -> None:
    branch = repo.branches[record.branch_name]
    if not branch.upstream:
        push_branch(origin, branch)
        update_upstream(repo, origin, branch)

    prs = gh.getPRs(record.branch_name)
    if prs and not all(p.closed for p in prs):
        for pr in prs:
            if gh.comment(pr):
                print(f"Commented {pr_number_with_style(pr)}.")
            else:
                print(f"Updated comment in {pr_number_with_style(pr)}.")

            gh.update_pr(record, pr)
            print(
                f"Set PR {pr_number_with_style(pr)} "
                + f"base branch to {emphasis(pr.base)}."
            )

    else:
        pr = gh.create_pr(
            record.get_parent().branch_name, record.branch_name, title, draft
        )
        print("Created draft PR ", pr_number_with_style(pr), ".", sep="")


class BadResult(Exception):
    def __init__(
        self, command: str, message: str = "", level=warning, *args: object
    ) -> None:
        super().__init__(*args)
        self.command = command
        self.message = message
        self.level = level
