import os
import json
import subprocess
import logging
import pygit2 as git
from urllib.parse import urlparse
from urllib.parse import ParseResult
from .styling import *
from .stack import *
from .args import Args
from .graphql import *

GH_SCHEME = "git@github.com:"

GH_TEMPLATES = [".github", "docs", ""]

COMMENT_FIRST_LINE = "Current dependencies on/for this PR:"


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
        for pr in self.getPRs(record.branch_name):
            if pr.number == remote_pr.number:
                if remote_pr.base != record.get_parent().branch_name:
                    logging.debug(
                        f"remote PR base doesn't match: {remote_pr.base} vs {record.get_parent().branch_name}"
                    )
                    return False
        return True

    def not_resolved(self, pr: PR) -> list[CodeThread]:
        result = [thread for thread in pr.threads if not thread.resolved]

        def author_reacted(thread: CodeThread) -> bool:
            if not thread.comments:
                return False
            for reaction in thread.comments[-1].reactions:
                if reaction.author.login == pr.author.login and reaction.content not in ["eyes", "confused"]:
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

    def pr_info(self, args: Args, record: Stack) -> list[str]:
        lines: list[str] = []
        for pr in self.getPRs(record.branch_name):
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
                    for p in self.getPRs(record.branch_name):
                        if p.number == pr.number:
                            if p.base != record.get_parent().branch_name:
                                vlines.append(
                                    with_style(
                                        "dim",
                                        warning("⟳ PR base ")
                                        + emphasis(p.base)
                                        + warning(" doesn't match branch parent ")
                                        + emphasis(record.get_parent().branch_name)
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

    def _find_stack_comment(self, pr: PR) -> Comment | None:
        for comment in pr.comments:
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

        heads = " ".join(
            f"head:{record.branch_name}"
            for record in self.stack.traverse()
            if record.get_parent()
        )
        if not heads:
            return prs

        def do(cursor: str):
            search = GQL_SEARCH.format(
                owner=self.owner, repository=self.repository, heads=heads, cursor=cursor
            )

            query = f"{GQL_QUERY} {{ {search} {{ {GQL_FIELDS} }} }}"
            response = graphql(self.token, query)
            edges = response["data"]["search"]["edges"]
            for edge in edges:
                pr_node = edge["node"]
                pr = make_pr(pr_node)
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
            cursor = '"' + edges[-1]["cursor"] + '"'
            logging.debug(f"Next cursor: {cursor}")
        return prs

    def comment(self, pr: PR):
        logging.debug(f"commenting pr #{pr.number}")
        comment = self._find_stack_comment(pr)
        md = self._make_stack_comment(pr)
        if comment:
            if comment.body == md:
                logging.debug("comment is up to date")
                return
            md = json.dumps(md, ensure_ascii=False)
            graphql(self.token, GQL_UPDATE_COMMENT.format(id=comment.id, body=md))
            print(f"Updated comment in {pr_number_with_style(pr)}.")
        else:
            md = json.dumps(md, ensure_ascii=False)
            graphql(self.token, GQL_ADD_COMMENT.format(pr_id=pr.id, body=md))
            print(f"Commented {pr_number_with_style(pr)}.")

    def update_pr(self, record: Stack, pr: PR):
        base = record.get_parent().branch_name
        if pr.base == base:
            return
        logging.debug(f"updating PR base from {pr.base} to {base}")
        graphql(self.token, GQL_UPDATE_PR_BASE.format(id=pr.id, base=base))
        pr.base = base
        print(f"Set PR {pr_number_with_style(pr)} base branch to {emphasis(base)}.")

    def create_pr(self, base: str, branch_name: str, title: str = "", draft: bool = False) -> any:
        logging.debug(f"creating PR wiht base {base} and head {branch_name}")
        base_branch = self.repo.lookup_branch(base)
        if not base_branch.upstream:
            raise Exception(f"Base branch {base} has no upstream.")
        repo_id_json = graphql(
            self.token,
            GQL_GET_REPO_ID.format(owner=self.owner, repository=self.repository),
        )

        pr_json = graphql(
            self.token,
            GQL_CREATE_PR.format(
                repository_id=repo_id_json["data"]["repository"]["id"],
                base=base,
                head=f"{self.owner}:{branch_name}",
                title=json.dumps(title or branch_name, ensure_ascii=False),
                draft="true" if draft else "false",
                body=json.dumps(self.template, ensure_ascii=False),
            ),
        )
        pr = make_pr(pr_json["data"]["createPullRequest"]["pullRequest"])
        if branch_name in self.__prs:
            self.__prs[branch_name].append(pr)
        else:
            self.__prs.update({branch_name: [pr]})
        print("Created draft PR ", pr_number_with_style(pr), ".", sep="")
        self.comment(pr)
        return pr


def initGH(repo: git.Repository, stack: Stack, offline: bool) -> GH | None:
    gh = GH(repo, stack) if not offline and is_gh(repo) else None
    if gh:
        logging.debug(f"found gh repository {gh.repository}")
    else:
        logging.debug("gh not found")
    return gh
