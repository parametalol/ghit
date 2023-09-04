import json
import logging
import os
import subprocess
from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse

import pygit2 as git

from . import graphql as gql
from .gh_graphql import (
    GQL_ADD_COMMENT,
    GQL_CREATE_PR,
    GQL_GET_REPO_ID,
    GQL_UPDATE_COMMENT,
    GQL_UPDATE_PR_BASE,
    PR,
    Author,
    Comment,
    Review,
    ReviewThread,
    graphql,
    make_pr,
    search_prs,
)
from .stack import Stack

GH_SCHEME = "git@github.com:"

GH_TEMPLATES = [".github", "docs", ""]

COMMENT_FIRST_LINE = "Current dependencies on/for this PR:"


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
        self.__prs = None

    def getPRs(self, branch_name: str) -> list[PR]:
        if self.__prs is None:
            self.__prs = self._search_stack_prs()
        return self.__prs.get(branch_name, list[PR]())

    def is_sync(self, remote_pr: PR, record: Stack) -> bool:
        if not record.get_parent():
            return True
        for pr in self.getPRs(record.branch_name):
            if pr.number == remote_pr.number:
                if remote_pr.base != record.get_parent().branch_name:
                    logging.debug(
                        "remote PR base doesn't match: "
                        + remote_pr.base
                        + " vs "
                        + record.get_parent().branch_name
                    )
                    return False
        return True

    def unresolved(pr: PR) -> dict[Author, list[Comment]]:
        result = [thread for thread in pr.threads.data if not thread.resolved]

        def author_reacted(thread: ReviewThread) -> bool:
            if not thread.comments.data:
                logging.debug("no comments?")
                return False
            for reaction in thread.comments.data[-1].reactions.data:
                if (
                    reaction.author.login == pr.author.login
                    and reaction.content not in ["EYES", "CONFUSED"]
                ):
                    logging.debug(
                        f"{thread.comments.data[-1].id}"
                        + f" author reacted with {reaction.content}"
                    )
                    return True
            logging.debug("author didn't react")
            return False

        def author_commented(thread: ReviewThread) -> bool:
            commented = (
                thread.comments.data
                and thread.comments.data[-1].author.login == pr.author.login
            )
            logging.debug(
                f"{thread.comments.data[-1].id} author commented={commented}"
            )
            return commented

        comments: dict[Author, list[Comment]] = {}
        for thread in filter(
            lambda cd: not author_commented(cd) and not author_reacted(cd),
            result,
        ):
            for c in thread.comments.data:
                if c.author in comments:
                    comments[c.author].append(c)
                else:
                    comments[c.author] = [c]
        return comments

    @dataclass
    class PRStats:
        unresolved: dict[Author, list[Comment]]
        change_requested: list[Review]
        approved: list[Review]
        in_sync: bool

    def pr_stats(self, record: Stack) -> dict[PR, PRStats]:
        stats: dict[PR, GH.PRStats] = {}
        for pr in self.getPRs(record.branch_name):
            authors: dict[str, Review] = {}
            for r in pr.reviews.data:
                authors[r.author.login] = r
            nr = GH.unresolved(pr)
            cr = [
                r for r in authors.values() if r.state == "CHANGES_REQUESTED"
            ]
            approved = [r for r in authors.values() if r.state == "APPROVED"]
            sync = self.is_sync(pr, record)
            stats[pr] = GH.PRStats(nr, cr, approved, sync)
        return stats

    def _find_stack_comment(self, pr: PR) -> Comment | None:
        for comment in pr.comments.data:
            if comment.body.startswith(COMMENT_FIRST_LINE):
                return comment
        return None

    def _make_stack_comment(self, remote_pr: PR) -> str:
        md = [COMMENT_FIRST_LINE, ""]
        for record in self.stack.traverse():
            prs = self.getPRs(record.branch_name)
            if prs:
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
            if not record.get_parent():
                prs[record.branch_name] = []

        heads = [
            record.branch_name
            for record in self.stack.traverse()
            if record.get_parent() or not record.length()
        ]
        for pr in search_prs(self.token, self.owner, self.repository, heads):
            if pr.head not in prs:
                prs.update({pr.head: [pr]})
            else:
                prs[pr.head].append(pr)

        logging.debug("Query done.")
        return prs

    def comment(self, pr: PR) -> bool:
        logging.debug(f"commenting pr #{pr.number}")
        comment = self._find_stack_comment(pr)
        md = self._make_stack_comment(pr)
        if comment and comment.body == md:
            logging.debug("comment is up to date")
            return
        md = json.dumps(md, ensure_ascii=False)
        if comment:
            graphql(
                self.token,
                GQL_UPDATE_COMMENT(gql.input(id=f'"{comment.id}"', body=md)),
            )
            return False
        graphql(
            self.token,
            GQL_ADD_COMMENT(gql.input(subjectId=f'"{pr.id}"', body=md)),
        )
        return True

    def update_pr(self, record: Stack, pr: PR) -> None:
        base = record.get_parent().branch_name
        if pr.base == base:
            return
        logging.debug(f"updating PR base from {pr.base} to {base}")
        graphql(
            self.token,
            GQL_UPDATE_PR_BASE(
                gql.input(pullRequestId=f'"{pr.id}"', baseRefName=f'"{base}"')
            ),
        )
        pr.base = base

    def create_pr(
        self, base: str, branch_name: str, title: str = "", draft: bool = False
    ) -> PR:
        logging.debug(f"creating PR wiht base {base} and head {branch_name}")
        base_branch = self.repo.lookup_branch(base)
        if not base_branch.upstream:
            raise Exception(f"Base branch {base} has no upstream.")
        repo_id_json = graphql(
            self.token,
            GQL_GET_REPO_ID(owner=self.owner, repository=self.repository),
        )

        repository_id = repo_id_json["data"]["repository"]["id"]
        head = f"{self.owner}:{branch_name}"
        title = json.dumps(title or branch_name, ensure_ascii=False)
        draft = "true" if draft else "false"
        body = json.dumps(self.template, ensure_ascii=False)

        pr_json = graphql(
            self.token,
            GQL_CREATE_PR(
                gql.input(
                    repositoryId=f'"{repository_id}"',
                    baseRefName=f'"{base}"',
                    headRefName=f'"{head}"',
                    title=title,
                    draft=draft,
                    body=body,
                )
            ),
        )
        pr = make_pr(
            {"node": pr_json["data"]["createPullRequest"]["pullRequest"]}
        )
        if branch_name in self.__prs:
            self.__prs[branch_name].append(pr)
        else:
            self.__prs.update({branch_name: [pr]})
        self.comment(pr)
        return pr


def initGH(repo: git.Repository, stack: Stack, offline: bool) -> GH | None:
    gh = GH(repo, stack) if not offline and is_gh(repo) else None
    if gh:
        logging.debug(f"found gh repository {gh.repository}")
    else:
        logging.debug("gh not found")
    return gh
