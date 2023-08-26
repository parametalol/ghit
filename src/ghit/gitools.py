from collections.abc import Iterator
import pygit2 as git
from .styling import *


def get_git_ssh_credentials() -> git.credentials.KeypairFromAgent:
    return git.KeypairFromAgent("git")

class MyRemoteCallback(git.RemoteCallbacks):
    def push_update_reference(self, refname, message):
        self.message = message
        self.refname = refname

    def credentials(self, url, username_from_url, allowed_types):
        return get_git_ssh_credentials()

def get_default_branch(repo: git.Repository) -> str:
    remote_head = repo.references["refs/remotes/origin/HEAD"].resolve().shorthand
    return remote_head.removeprefix("origin/")


def get_current_branch(repo: git.Repository) -> git.Branch:
    return repo.lookup_branch(repo.head.resolve().shorthand)


def last_commits(
    repo: git.Repository, target: git.Oid, n: int = 1
) -> Iterator[git.Commit]:
    i = 0
    for commit in repo.walk(target):
        yield commit
        i += 1
        if i >= n:
            break


def checkout(repo: git.Repository, parent_name: str | None, branch_name: str | None):
    branch = repo.branches.get(branch_name) if branch_name else None
    if not branch:
        print(danger("Error:"), emphasis(branch_name), danger("not found in local."))
        return
    repo.checkout(branch)
    print(f"Checked-out {emphasis(branch.branch_name)}.")
    if parent_name:
        parent_branch = repo.branches[parent_name]
        a, _ = repo.ahead_behind(parent_branch.target, branch.target)
        if a:
            print(f"This branch has fallen back behind {emphasis(parent_name)}.")
            print("You may want to restack to pick up the following commits:")
            for commit in last_commits(repo, parent_branch.target, a):
                print(
                    inactive(f"\t[{commit.short_id}] {commit.message.splitlines()[0]}")
                )

    if not branch.upstream:
        print("The branch doesn't have an upstream.")
        return
    a, b = repo.ahead_behind(
        branch.target,
        branch.upstream.target,
    )
    if a:
        print(
            f"Following local commits are missing in upstream {emphasis(branch.upstream.branch_name)}:"
        )
        for commit in last_commits(repo, branch.target, a):
            print(inactive(f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"))
    if b:
        print(
            f"Following upstream commits are missing in local {emphasis(branch.branch_name)}:"
        )
        for commit in last_commits(repo, branch.upstream.target, b):
            print(inactive(f"\t[{commit.short_id}] {commit.message.splitlines()[0]}"))
