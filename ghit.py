#!/usr/bin/env python
import os, argparse, requests
import pygit2

GH_TOKEN = "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"
GH_HEADERS = {
    "Authorization": "Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


Stack = list[str]


def red(m: str) -> str:
    return f"\033[31m{m}\033[0m"


def green(m: str) -> str:
    return f"\033[32m{m}\033[0m"


def yellow(m: str) -> str:
    return f"\033[33m{m}\033[0m"


def blue(m: str) -> str:
    return f"\033[34m{m}\033[0m"


def open_stack(filename: str) -> Stack:
    with open(filename) as f:
        return [s.strip() for s in f.readlines()]


def gh(endpoint: str, params: dict) -> str:
    owner = "stackrox"
    repo = "stackrox"
    response = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}/{endpoint}",
        params,
        headers=GH_HEADERS,
    )
    if response.ok:
        return response.json()
    else:
        raise BaseException(response.text)


def get_PR(branch: str):
    return gh("pulls", {"head": f"stackrox:{branch}"})


def ls(repo: pygit2.Repository, stack: Stack, offline: bool):
    current = get_current_branch(repo)
    prev = get_default_branch(repo)
    for branch in stack:
        a, b = repo.ahead_behind(repo.references[f"refs/heads/{prev}"].target,
                                 repo.references[f"refs/heads/{branch}"].target)
        
        pfx = " " if a == 0 else "'"
            
        if not offline:
            pr = get_PR(branch)
        pfx += "→ " if branch == current else "  "
        if offline or len(pr) == 0:
            print(pfx, branch)
        else:
            pr = pr[0]
            state = {"open": green, "closed": red, "merged": blue}[pr["state"]]

            print(f"{pfx}{branch}", state(f"#{pr['number']} ({pr['title']})"))
        prev = branch


def get_default_branch(repo: pygit2.Repository) -> str:
    branch = repo.references["refs/remotes/origin/HEAD"].resolve().shorthand
    return branch[len("origin/") :] if branch.startswith("origin/") else branch


def get_current_branch(repo: pygit2.Repository) -> str:
    return repo.head.resolve().shorthand


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("-s", "--stack", default=os.getenv("GHIT_STACK"))
    parser.add_argument("-r", "--repository", default=".")
    parser.add_argument("-o", "--offline", action="store_true")

    args = parser.parse_args()
    if args.command in ["ls", "list"]:
        stack = open_stack(args.stack)
        repo = pygit2.Repository(args.repository)
        # print("default branch:", get_default_branch(repo))
        # print("current branch:", get_current_branch(repo))

        ls(repo, stack, args.offline)


main()
