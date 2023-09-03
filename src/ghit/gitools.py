from collections.abc import Iterator
import pygit2 as git
from .styling import danger, emphasis, inactive
from .stack import Stack


def get_git_ssh_credentials() -> git.credentials.KeypairFromAgent:
    return git.KeypairFromAgent("git")


class MyRemoteCallback(git.RemoteCallbacks):
    def __init__(self, credentials=None, certificate=None):
        super().__init__(credentials or get_git_ssh_credentials(), certificate)
        self.message = ""

    def push_update_reference(self, refname, message):
        self.message = message
        self.refname = refname


def get_default_branch(repo: git.Repository) -> str:
    remote_head = (
        repo.references["refs/remotes/origin/HEAD"].resolve().shorthand
    )
    return remote_head.removeprefix("origin/")


def get_current_branch(repo: git.Repository) -> git.Branch:
    return repo.lookup_branch(repo.head.resolve().shorthand)


def last_commits(
    repo: git.Repository, target: git.Oid, n: int = 1
) -> Iterator[git.Commit]:
    for i, commit in enumerate(repo.walk(target), start=1):
        yield commit
        if i >= n:
            break


def print_branch_info(
    repo: git.Repository, record: Stack, branch: git.Branch
) -> None:
    if not record.get_parent():
        return
    parent_branch = repo.branches[record.get_parent().branch_name]
    a, _ = repo.ahead_behind(parent_branch.target, branch.target)
    if a:
        print(
            "This branch has fallen back behind "
            + emphasis(record.get_parent().branch_name)
            + "."
        )
        print("You may want to restack to pick up the following commits:")
        for commit in last_commits(repo, parent_branch.target, a):
            print(
                inactive(
                    f"\t[{commit.short_id}] " + commit.message.splitlines()[0]
                )
            )


def print_upstream_info(repo: git.Repository, branch: git.Branch) -> None:
    if not branch.upstream:
        print("The branch doesn't have an upstream.")
        return
    a, b = repo.ahead_behind(
        branch.target,
        branch.upstream.target,
    )
    if a:
        print(
            "Following local commits are missing in upstream "
            + emphasis(branch.upstream.branch_name)
            + ":"
        )
        for commit in last_commits(repo, branch.target, a):
            print(
                inactive(
                    f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"
                )
            )
    if b:
        print(
            "Following upstream commits are missing in local "
            + emphasis(branch.branch_name)
            + ":"
        )
        for commit in last_commits(repo, branch.upstream.target, b):
            print(
                inactive(
                    f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"
                )
            )


def checkout(repo: git.Repository, record: Stack) -> None:
    branch_name = record.branch_name
    branch = repo.branches.get(branch_name) if branch_name else None
    if not branch:
        print(
            danger("Error:"),
            emphasis(branch_name),
            danger("not found in local."),
        )
        remote = repo.branches.remote["origin/" + branch_name]
        if remote:
            print(
                "There is though a remote branch "
                + emphasis(remote.branch_name)
                + "."
            )
        return
    repo.checkout(branch)
    print(f"Checked-out {emphasis(branch.branch_name)}.")
    print_branch_info(repo, record, branch)
    print_upstream_info(repo, branch)
