import requests
import os
import subprocess
import logging
import pygit2 as git
from urllib.parse import urlparse
from urllib.parse import ParseResult
from .styling import *
from .stack import *

GH_SCHEME = "git@github.com:"

GH_TEMPLATES = [".github", "docs", ""]

COMMENT_FIRST_LINE = "Current dependencies on/for this PR:"

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


def pr_number_with_style(pr: any) -> str:
    line: list[str] = []
    if pr["locked"]:
        line.append("🔒")
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    if pr["draft"]:
        line.append(style("draft"))
    line.append(style(f'#{pr["number"]}'))
    return " ".join(line)


def pr_title_with_style(pr: any) -> str:
    style = lambda m: with_style("dim", pr_state_style[pr_state(pr)](m))
    return style(pr["title"])


def pr_with_style(pr: any) -> str:
    return pr_number_with_style(pr) + " " + pr_title_with_style(pr)


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


def is_sync(pr: any, branch: git.Branch) -> bool:
    return not branch or pr["head"]["sha"] == branch.target.hex


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
            if is_sync(prs[0], branch):
                return warning("⟳") + pr_with_style(prs[0])
            return pr_with_style(prs[0])
        return ", ".join(
            (
                warning("⟳") + pr_number_with_style(pr)
                if is_sync(prs[0], branch)
                else pr_number_with_style(pr)
            )
            for pr in prs
        )

    def _find_comment(self, pr: int) -> any:
        comments = self._call(f"issues/{pr}/comments")
        for comment in comments:
            if str(comment["body"]).startswith(COMMENT_FIRST_LINE):
                return comment
        return None

    def _make_comment(self, current_pr_number: int) -> str:
        md = [COMMENT_FIRST_LINE, ""]
        for record in self.stack.traverse():
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

    def comment(self, branch: git.Branch, new: bool = False):
        for pr in self.find_PRs(branch.branch_name):
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
                print(f"Updated comment in {pr_number_with_style(branch, pr)}.")
            else:
                self._call(
                    f"issues/{pr['number']}/comments",
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
        if branch_name in pr_cache:
            pr_cache[branch_name].append(pr)
        else:
            pr_cache[branch_name] = [pr]
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
