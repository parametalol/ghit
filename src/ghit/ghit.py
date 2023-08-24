#!/usr/bin/env python3

import os
import argparse
import requests
import subprocess
import logging
import pygit2 as git
from urllib.parse import urlparse
from urllib.parse import ParseResult
from collections.abc import Iterator


class Args:
    stack: str
    repository: str
    offline: bool
    title: str
    debug: bool


COMMENT_FIRST_LINE = "Current dependencies on/for this PR:"

# region style

COLORS: dict[str, int] = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "light gray": 37,
    "default": 39,
    "dark gray": 90,
    "light red": 91,
    "light green": 92,
    "light yellow": 93,
    "light blue": 94,
    "light magenta": 95,
    "light cyan": 96,
    "white": 97,
}
STYLES: dict[str, int] = {
    "bold": 1,
    "dim": 2,
    "underlined": 4,
    "blink": 5,
    "reverse": 7,
    "hidden": 8,
    "strikethrough": 9,
}
ESC = "\033"


def with_color(color: str, m: str) -> str:
    return f"{ESC}[{COLORS[color]}m{m}{ESC}[{COLORS['default']}m"


def with_style(style: str, m: str) -> str:
    return f"{ESC}[{STYLES[style]}m{m}{ESC}[0m"


def normal(m: str) -> str:
    return m


def deleted(m: str) -> str:
    return with_style("strikethrough", m)


def inactive(m: str) -> str:
    return with_color("dark gray", m)


def danger(m: str) -> str:
    return with_color("red", m)


def good(m: str) -> str:
    return with_color("green", m)


def warning(m: str) -> str:
    return with_color("yellow", m)


def calm(m: str) -> str:
    return with_color("light blue", m)


def colorful(m: str) -> str:
    return with_color("magenta", m)


def emphasis(m: str) -> str:
    return with_color("cyan", m)


# endregion style

# region stack

Stack = dict[str, any]


class StackRecord:
    branch_name: str | None
    depth: int
    children: int
    sibling_index: int

    def __init__(
        self,
        branch: str | None = None,
        depth: int = 0,
        children: int = 0,
        index: int = 0,
    ) -> None:
        self.branch_name = branch
        self.depth = depth
        self.children = children
        self.index = index


def add_child(stack: Stack, parents: list[str], child: str):
    if child.startswith("#"):
        return
    branch = child.lstrip(".")
    depth = len(child) - len(branch)
    for _ in range(0, len(parents) - depth):
        parents.pop()
    parents.append(branch)
    for p in range(0, depth):
        stack = stack[parents[p]]
    stack[branch] = {}


def connect(args: Args) -> tuple[git.Repository, Stack]:
    repo = git.Repository(args.repository)
    if repo.is_empty:
        return repo, None
    stack = open_stack(args.stack)
    if not stack:
        stack = Stack()
        current = get_current_branch(repo)
        stack[current.branch_name] = {}
    return repo, stack


def open_stack(filename: str) -> Stack:
    if not os.path.isfile(filename):
        return None
    stack = Stack()
    parents = list[str]()
    with open(filename) as f:
        for line in f.readlines():
            add_child(stack, parents, line.rstrip())
    return stack


def traverse(
    stack: Stack, parent: StackRecord = None, depth: int = 0
) -> Iterator[tuple[StackRecord, StackRecord]]:
    i = 0
    for k, v in stack.items():
        current = StackRecord(k, depth, len(v), i)
        yield parent, current
        i += 1
        if len(v) > 0:
            yield from traverse(v, current, depth + 1)


# endregion stack

# region GH

GH_SCHEME = "git@github.com:"

GH_TEMPLATES = [".github", "docs", ""]

pr_cache = dict[str, list[any]]()

pr_state_style = {
    "OPEN": good,
    "CLOSED": lambda m: danger(deleted(m)),
    "MERGED": calm,
    "DRAFT": inactive,
}


def pr_state(pr) -> str:
    if pr["draft"]:
        return "DRAFT"
    if pr["merged_at"]:
        return "MERGED"
    return str(pr["state"]).upper()


def pr_number_with_style(branch: git.Branch, pr: any) -> str:
    line: list[str] = []
    if pr["locked"]:
        line.append("🔒")
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    if pr["draft"]:
        line.append(style("draft"))
    if not branch or pr["head"]["sha"] != branch.target.hex:
        line.append(warning("⟳"))
    line.append(style(f'#{pr["number"]}'))
    return " ".join(line)


def pr_title_with_style(pr: any) -> str:
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    return style(pr["title"])


def get_gh_owner_repository(url: ParseResult) -> (str, str):
    _, owner, repository = url.path.split("/", 2)
    return owner, repository.removesuffix(".git")


def get_gh_url(repo: git.Repository) -> ParseResult:
    url: str = repo.remotes["origin"].url
    if url.startswith(GH_SCHEME):
        insteadof = repo.config["url.git@github.com:.insteadof"]
        url = insteadof + url.removeprefix(GH_SCHEME)
    return urlparse(url)


def get_gh_token(url: ParseResult) -> str:
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    p = subprocess.run(
        args=["git", "credential", "fill"],
        input=f"protocol={url.scheme}\nhost={url.netloc}\n",
        capture_output=True,
        text=True,
    )
    credentials = {}
    if p.returncode == 0:
        for line in p.stdout.splitlines():
            k, v = line.split("=", 1)
            credentials[k] = v
    return credentials["password"]


def is_gh(repo: git.Repository) -> bool:
    if repo.is_empty or repo.is_bare:
        return False
    url = get_gh_url(repo)
    return url.netloc.find("github.com") >= 0


class GH:
    repo: git.Repository
    owner: str
    repository: str
    url: ParseResult
    token: git.credentials.UserPass
    stack: Stack
    template: str | None

    def __init__(self, repo: git.Repository, stack: Stack) -> None:
        self.stack = stack
        self.repo = repo
        self.url = get_gh_url(repo)
        self.owner, self.repository = get_gh_owner_repository(self.url)
        self.token = get_gh_token(self.url)
        for t in GH_TEMPLATES:
            filename = os.path.join(repo.path, t, "pull_request_template.md")
            if os.path.exists(filename):
                self.template = open(filename).read()
                break
        else:
            self.template = None

    def _call(
        self,
        endpoint: str,
        params: dict[str, str] = {},
        body: any = None,
        method: str = "GET",
    ) -> str:
        response = requests.request(
            method,
            url=f"https://api.github.com/repos/{self.owner}/{self.repository}/{endpoint}",
            params=params,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=body,
        )
        if not response.ok:
            raise BaseException(response.text)
        return response.json()

    def find_PRs(self, branch: str) -> list[any]:
        if branch not in pr_cache:
            logging.debug(f"branch {branch} not in cache")
            pr = self._call("pulls", {"head": f"{self.owner}:{branch}", "state": "all"})
            logging.debug(f"gh found prs: {len(pr)}")
            pr_cache[branch] = pr
        return pr_cache[branch]

    def pr_info(self, branch_name: str) -> str | None:
        prs = self.find_PRs(branch_name)
        branch = self.repo.branches.get(branch_name)
        if len(prs) == 1:
            return " ".join(
                [pr_number_with_style(branch, prs[0]), pr_title_with_style(prs[0])]
            )
        return ", ".join(pr_number_with_style(branch, pr) for pr in prs)

    def _find_comment(self, pr: int) -> any:
        comments = self._call(f"issues/{pr}/comments")
        for comment in comments:
            if str(comment["body"]).startswith(COMMENT_FIRST_LINE):
                return comment
        return None

    def _make_comment(self, current_pr_number: int) -> str:
        md = [COMMENT_FIRST_LINE, ""]
        for _, record in traverse(self.stack):
            prs = self.find_PRs(record.branch_name)
            if prs is not None and len(prs) > 0:
                for pr in prs:
                    line = "  " * record.depth + f"* **PR #{pr['number']}**"
                    if pr["number"] == current_pr_number:
                        line += " 👈"
                    md.append(line)
            else:
                md.append("  " * record.depth + f"* {record.branch_name}")
        return "\n".join(md)

    def comment(self, branch: git.Branch, new: bool = False) -> list[any]:
        prs = self.find_PRs(branch.branch_name)
        for pr in prs:
            comment = self._find_comment(pr["number"]) if not new else None
            md = self._make_comment(pr["number"])
            if comment is not None:
                if comment["body"] == md:
                    continue
                self._call(
                    f"issues/comments/{comment['id']}",
                    None,
                    {"body": md},
                    "PATCH",
                )
                print(
                    "Updated comment in ",
                    pr_number_with_style(branch, pr),
                    ".",
                    sep="",
                )
            else:
                self._call(
                    f"issues/{pr['number']}/comments",
                    None,
                    {"body": md},
                    "POST",
                )
                print(
                    "Commented ",
                    pr_number_with_style(branch, pr),
                    ".",
                    sep="",
                )
        return prs

    def create_pr(self, base: str, branch_name: str, title: str = "") -> any:
        pr = self._call(
            endpoint="pulls",
            method="POST",
            body={
                "title": title or branch_name,
                "base": base,
                "head": f"{self.owner}:{branch_name}",
                "body": self.template,
                "draft": True,
            },
        )
        if branch_name in pr_cache:
            pr_cache[branch_name].append(pr)
        else:
            pr_cache[branch_name] = [pr]
        branch = self.repo.lookup_branch(branch_name)
        print("Created draft PR ", pr_number_with_style(branch, pr), ".", sep="")
        self.comment(branch, True)
        return pr


def get_GH(repo: git.Repository, stack: Stack, offline: bool) -> GH | None:
    gh = GH(repo, stack) if not offline and is_gh(repo) else None
    if gh:
        logging.debug(f"found gh repository {gh.repository}")
    else:
        logging.debug("gh not found")
    return gh


# endregion GH


# region git


def get_git_ssh_credentials() -> git.credentials.KeypairFromAgent:
    return git.KeypairFromAgent("git")


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


def checkout(repo: git.Repository, parent: StackRecord, branch_name: str | None):
    if branch_name is None:
        return
    branch = repo.branches.get(branch_name)
    if not branch:
        print(danger("Error:"), emphasis(branch_name), danger("not found in local."))
        return
    repo.checkout(branch)
    print(f"Checked-out {emphasis(branch_name)}.")
    if parent is not None:
        parent_branch = repo.branches[parent.branch_name]
        a, _ = repo.ahead_behind(parent_branch.target, branch.target)
        if a:
            print(f"This branch has fallen back behind {emphasis(parent.branch_name)}.")
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


# endregion git


# region commands


def ls(args: Args):
    repo, stack = connect(args)
    if repo.is_empty:
        return

    checked_out = get_current_branch(repo).branch_name
    parent_prefix: list[str] = []

    gh = get_GH(repo, stack, args.offline)

    for parent, record in traverse(stack):
        parent_prefix = parent_prefix[: record.depth - 1]
        current = record.branch_name == checked_out
        last_child = record.index == parent.children - 1 if parent else False

        line = _print_line(
            repo, current, parent_prefix, parent, record.branch_name, last_child
        )
        if gh:
            info = gh.pr_info(record.branch_name)
            if info:
                line.append(info)

        print(" ".join(line))
        if parent is not None:
            parent_prefix.append("  " if record.index == parent.children - 1 else "│ ")


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
                line.append(with_style("dim", "↕" if a and b else "↑" if a else "↓"))
        else:
            line.append(line_color("*"))

    return line


def _move(args: Args, command: str):
    repo, stack = connect(args)
    to_checkout_name = get_current_branch(repo).branch_name
    parent: StackRecord = None

    pick_next: bool = False
    prev_name: str | None = None
    for parent, record in traverse(stack):
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
    for parent, record in traverse(stack):
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
    for parent, record in traverse(stack):
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


def pr_sync(args: Args):
    repo, stack = connect(args)

    if repo.is_empty:
        return

    gh = get_GH(repo, stack, args.offline)
    if gh is None:
        return
    for parent, record in traverse(stack):
        if parent is None:
            continue
        prs = gh.find_PRs(record.branch_name)
        if len(prs) == 0:
            gh.create_pr(parent.branch_name, record.branch_name)
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

    for parent, record in traverse(stack):
        if parent is None:
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
    gh = get_GH(repo, stack, args.offline)
    if gh is None:
        return
    origin = repo.remotes["origin"]
    if not origin:
        return
    current = get_current_branch(repo)
    for parent, record in traverse(stack):
        if record.branch_name == current.branch_name:
            branch = repo.branches[record.branch_name]
            if not branch.upstream:
                update_upstream(repo, origin, branch)
            prs = gh.find_PRs(record.branch_name)
            if len(prs) == 0:
                gh.create_pr(parent.branch_name, record.branch_name, args.title)
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
