from dataclasses import dataclass
import requests
import os
import subprocess
import logging
import pygit2 as git
from urllib.parse import urlparse
from urllib.parse import ParseResult
from .styling import *
from .stack import *
from .args import Args

GH_SCHEME = "git@github.com:"

GH_TEMPLATES = [".github", "docs", ""]

COMMENT_FIRST_LINE = "Current dependencies on/for this PR:"


@dataclass
class Author:
    login: str
    name: str | None

    def __str__(self) -> str:
        if self.name and self.login:
            return f"{self.name} ({self.login})"
        return self.name or self.login


@dataclass
class Reaction:
    content: str
    author: Author


@dataclass
class Comment:
    author: Author
    body: str
    reacted: bool
    url: str
    reactions: list[Reaction]


@dataclass
class CodeThread:
    path: str
    resolved: bool
    outdated: bool
    comments: list[Comment]


@dataclass
class Review:
    author: Author
    state: str
    url: str


@dataclass
class PR:
    number: int
    author: Author
    title: str
    state: str
    closed: bool
    merged: bool
    locked: bool
    draft: bool
    base: str
    head: str
    threads: list[CodeThread]
    comments: list[Comment]
    reviews: list[Review]


# region style

pr_state_style = {
    "OPEN": good,
    "CLOSED": lambda m: danger(deleted(m)),
    "MERGED": calm,
    "DRAFT": inactive,
}


def pr_state(pr: PR) -> str:
    if pr.draft:
        return "DRAFT"
    if pr.merged:
        return "MERGED"
    return str(pr.state).upper()


def pr_number_with_style(pr: PR) -> str:
    line: list[str] = []
    if pr.locked:
        line.append("🔒")
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    line.append(style(f"#{pr.number} ({pr_state(pr)})"))
    return " ".join(line)


def pr_title_with_style(pr: PR) -> str:
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    return style(pr.title)


def pr_with_style(pr: PR) -> str:
    return pr_number_with_style(pr) + " " + pr_title_with_style(pr)


# endregion style

# region query
GQL_QUERY = "query searh_prs"
GQL_SEARCH = """
    search(
        query: "repo:{owner}/{repository} is:pr {heads}"
        type: ISSUE
        first: 20
        after: {cursor}
    )
"""

GQL_FIELDS = """
edges {
    cursor
    node {
    ... on PullRequest {
        number
        title
        author {
            login
            ... on User {
                name
            }
        }
        baseRefName
        headRefName
        isDraft
        locked
        closed
        merged
        state

        comments(first: 10) {
            nodes {
                author {
                    login
                    ... on User {
                        name
                    }
                }
                url
                body
                minimizedReason
                reactions(last: 10) {
                    nodes {
                        content
                        user {
                            login
                            name
                        }
                    }
                }
            }
        }

        reviewThreads(last: 10) {
            nodes {
                path
                isResolved
                isOutdated
                comments(last: 1) {
                    nodes {
                        path
                        url
                        author {
                            login
                            ... on User {
                                name
                            }
                        }
                        body
                        reactions(last: 10) {
                            nodes {
                                content
                                user {
                                    login
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }

        reviews(last: 10) {
            nodes {
                state
                url
                author {
                    login
                    ... on User {
                        name
                    }
                }
            }
        }
    } }
}
"""


def _make_author(node: any) -> Author:
    return Author(
        login=node["login"],
        name=node["name"] if "name" in node else None,
    )


def _make_reaction(node: any) -> Reaction:
    return Reaction(
        content=node["content"],
        author=_make_author(node["user"]),
    )


def _make_comment(node: any) -> Comment:
    return Comment(
        author=_make_author(node["author"]),
        body=node["body"],
        reacted=False,
        url=node["url"],
        reactions=[_make_reaction(reaction) for reaction in node["reactions"]["nodes"]],
    )


def _make_review(node: any) -> Review:
    return Review(
        author=_make_author(node["author"]), state=node["state"], url=node["url"]
    )


def _make_thread(node: any) -> CodeThread:
    return CodeThread(
        path=node["path"],
        resolved=node["isResolved"],
        outdated=node["isOutdated"],
        comments=[_make_comment(comment) for comment in node["comments"]["nodes"]],
    )


def _make_pr(node: any) -> PR:
    return PR(
        number=node["number"],
        author=_make_author(node["author"]),
        title=node["title"],
        draft=node["isDraft"],
        locked=node["locked"],
        closed=node["closed"],
        merged=node["merged"],
        state=node["state"],
        base=node["baseRefName"],
        head=node["headRefName"],
        comments=[_make_comment(n) for n in node["comments"]["nodes"]],
        threads=[_make_thread(n) for n in node["reviewThreads"]["nodes"]],
        reviews=[_make_review(n) for n in node["reviews"]["nodes"]],
    )


# endregion query


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


def _graphql(token: str, query: str) -> any:
    response = requests.post(
        url=f"https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"query": query},
    )
    if not response.ok:
        raise BaseException(response.text)
    return response.json()


class GH:
    def __init__(self, repo: git.Repository, stack: Stack) -> None:
        self.stack = stack
        self.repo = repo
        self.url = get_gh_url(repo)
        self.owner, self.repository = get_gh_owner_repository(self.url)
        self.token = get_gh_token(self.url)
        self.template: str | None = None
        for t in GH_TEMPLATES:
            filename = os.path.join(repo.path, t, "pull_request_template.md")
            if os.path.exists(filename):
                self.template = open(filename).read()
                break
        self.prs = self._search_stack_prs()

    def _call(
        self,
        endpoint: str,
        params: dict[str, str] = {},
        body: any = None,
        method: str = "GET",
    ) -> any:
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

    def is_sync(self, remote_pr: PR, record: StackRecord) -> bool:
        for pr in self.prs[record.branch_name]:
            if pr.number == remote_pr.number:
                if remote_pr.base != record.parent.branch_name:
                    logging.debug(
                        f"remote PR base doesn't match: {remote_pr.base} vs {record.parent.branch_name}"
                    )
                    return False
        return True

    def not_resolved(self, pr: PR) -> list[CodeThread]:
        result = [thread for thread in pr.threads if not thread.resolved]

        def author_reacted(thread: CodeThread) -> bool:
            if not thread.comments:
                return False
            for reaction in thread.comments[-1].reactions:
                if reaction.author.login == pr.author.login:
                    return True
            return False

        def author_commented(thread: CodeThread) -> bool:
            return (
                thread.comments and thread.comments[-1].author.login == pr.author.login
            )

        return list(
            filter(
                lambda cd: not author_commented(cd) and not author_reacted(cd), result
            )
        )

    def pr_info(self, args: Args, record: StackRecord) -> list[str]:
        lines: list[str] = []
        for pr in self.prs[record.branch_name]:
            line = [pr_number_with_style(pr)]
            nr = self.not_resolved(pr)
            if not args.verbose and nr:
                line.append(warning("!"))
            cr = [r for r in pr.reviews if r.state and r.state == "CHANGES_REQUESTED"]
            if not args.verbose and cr:
                line.append(danger("✗"))
            approved = [r for r in pr.reviews if r.state == "APPROVED"]
            if not args.verbose and not cr and approved:
                line.append(good("✓"))
            sync = self.is_sync(pr, record)
            if not args.verbose and not sync:
                line.append(warning("⟳"))
            line.append(" ")
            line.append(pr_title_with_style(pr))
            lines.append("".join(line))
            if args.verbose:
                vlines = []
                for r in approved:
                    vlines.append(
                        with_style("dim", good("✓ Approved by "))
                        + with_style("italic", good(str(r.author)))
                        + with_style("dim", good(".")),
                    )

                if not sync:
                    for p in self.prs[record.branch_name]:
                        if p.number == pr.number:
                            if p.base != record.parent.branch_name:
                                vlines.append(
                                    with_style(
                                        "dim",
                                        warning("⟳ PR base ")
                                        + emphasis(p.base)
                                        + warning(" doesn't match branch parent ")
                                        + emphasis(record.parent.branch_name)
                                        + warning("."),
                                    )
                                )
                if nr:
                    for thread in nr:
                        for c in thread.comments:
                            vlines.append(
                                with_style(
                                    "dim", warning("! No reaction to a comment by ")
                                )
                                + with_style("italic", warning(str(c.author)))
                                + with_style("dim", warning(":")),
                            )
                            vlines.append(f"  {colorful(c.url)}")
                if cr:
                    for review in cr:
                        vlines.append(
                            with_style("dim", danger("✗ Changes requested by "))
                            + with_style("italic", danger(str(review.author)))
                            + with_style("dim", danger(":")),
                        )
                        vlines.append(f"  {colorful(review.url)}")
                lines.extend(vlines)

        return lines

    def _find_stack_comment(self, pr: PR) -> any:
        for comment in pr.comments:
            if comment.body.startswith(COMMENT_FIRST_LINE):
                return comment
        return None

    def _make_stack_comment(self, remote_pr: PR) -> str:
        md = [COMMENT_FIRST_LINE, ""]
        for record in self.stack.traverse():
            prs = self.prs[record.branch_name]
            if prs is not None and len(prs) > 0:
                for pr in prs:
                    line = "  " * record.depth + f"* **PR #{pr.number}**"
                    if pr.number == remote_pr.number:
                        line += " 👈"
                    md.append(line)
            else:
                md.append("  " * record.depth + f"* {record.branch_name}")
        return "\n".join(md)

    def _search_stack_prs(self) -> dict[str, list[PR]]:
        prs = dict[str, list[PR]]()
        for record in self.stack.traverse():
            if not record.parent:
                prs[record.branch_name] = []

        heads = " ".join(
            f"head:{record.branch_name}"
            for record in self.stack.traverse()
            if record.parent
        )

        def do(cursor: str):
            search = GQL_SEARCH.format(
                owner=self.owner, repository=self.repository, heads=heads, cursor=cursor
            )

            query = f"{GQL_QUERY} {{ {search} {{ {GQL_FIELDS} }} }}"
            response = _graphql(self.token, query)
            edges = response["data"]["search"]["edges"]
            for edge in edges:
                pr_node = edge["node"]
                pr = _make_pr(pr_node)
                if pr.head not in prs:
                    prs.update({pr.head: [pr]})
                else:
                    prs[pr.head].append(pr)
            return edges

        cursor = "null"
        while True:
            edges = do(cursor)
            if not edges:
                logging.debug("Query done.")
                break
            cursor = '"'+edges[-1]["cursor"]+'"'
            logging.debug(f"Next cursor: {cursor}")
        return prs

    def comment(self, branch: git.Branch, new: bool = False):
        for pr in self.prs[branch.branch_name]:
            comment = self._find_stack_comment(pr) if not new else None
            md = self._make_stack_comment(pr)
            if comment is not None:
                if comment["body"] == md:
                    continue
                self._call(
                    f"issues/comments/{comment['id']}",
                    None,
                    {"body": md},
                    "PATCH",
                )
                print(f"Updated comment in {pr_number_with_style(branch, pr)}.")
            else:
                self._call(
                    f"issues/{pr.number}/comments",
                    None,
                    {"body": md},
                    "POST",
                )
                print(f"Commented {pr_number_with_style(branch, pr)}.")

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
        if branch_name in self.prs:
            self.prs[branch_name].append(pr)
        else:
            self.prs.update({branch_name: [pr]})
        branch = self.repo.lookup_branch(branch_name)
        print("Created draft PR ", pr_number_with_style(branch, pr), ".", sep="")
        self.comment(branch, True)
        return pr


def initGH(repo: git.Repository, stack: Stack, offline: bool) -> GH | None:
    gh = GH(repo, stack) if not offline and is_gh(repo) else None
    if gh:
        logging.debug(f"found gh repository {gh.repository}")
    else:
        logging.debug("gh not found")
    return gh
