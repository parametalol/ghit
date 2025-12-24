from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import ParseResult, urlparse

from . import gh_graphql as ghgql
from . import graphql as gql
from .error import GhitError

if TYPE_CHECKING:
    import pygit2 as git

    from .stack import Stack

GH_SCHEME = 'git@github.com:'

GH_TEMPLATES = ['.github', 'docs', '']

COMMENT_BEGIN = '<!-- GHIT dependencies begin -->'
COMMENT_FIRST_LINE = 'Current dependencies on/for this PR:'
COMMENT_END = '<!-- GHIT dependencies end -->'


def get_gh_owner_repository(url: ParseResult) -> tuple[str, str]:
    _, owner, repository = url.path.split('/', 2)
    return owner, repository.removesuffix('.git')


def get_gh_url(repo: git.Repository) -> ParseResult:
    url: str | None = repo.remotes['origin'].url
    if url is None:
        raise GhitError('empty remote origin URL')
    if url.startswith(GH_SCHEME):
        insteadof = repo.config['url.git@github.com:.insteadof']
        url = insteadof + url.removeprefix(GH_SCHEME)
    return urlparse(url)


def get_gh_token(url: ParseResult) -> str:
    token = os.getenv('GITHUB_TOKEN')
    if token:
        return token
    p = subprocess.run(
        args=['git', 'credential', 'fill'],
        input=f'protocol={url.scheme}\nhost={url.netloc}\n',
        capture_output=True,
        text=True,
        check=True,
    )
    credentials = {}
    if p.returncode == 0:
        for line in p.stdout.splitlines():
            k, v = line.split('=', 1)
            credentials[k] = v
    return credentials['password']


def is_gh(repo: git.Repository) -> bool:
    if repo.is_empty or repo.is_bare:
        return False
    url = get_gh_url(repo)
    return url.netloc.find('github.com') >= 0


def _find_stack_comment(body: str) -> tuple[int, int] | None:
    start_index = body.find(COMMENT_BEGIN)
    if start_index == -1:
        return None
    end_index = body.find(COMMENT_END, start_index)
    if end_index == -1:
        return None
    end_index += len(COMMENT_END)
    return (start_index, end_index)


def _patch_body(body: str, comment: str) -> str | None:
    range = _find_stack_comment(body)
    if range:
        if body[range[0] : range[1]] == comment:
            return None
        return body[: range[0]] + comment + body[range[1] :]
    return body + '\n' + comment


class GH:
    def __init__(self, repo: git.Repository, stack: Stack) -> None:
        self.stack = stack
        self.repo = repo
        self.url = get_gh_url(repo)
        self.owner, self.repository = get_gh_owner_repository(self.url)
        self.token = get_gh_token(self.url)
        self.template: str | None = None
        for t in GH_TEMPLATES:
            filename = Path(repo.workdir) / t / 'pull_request_template.md'
            if filename.exists():
                self.template = filename.open().read()
                logging.debug('found PR template: %s', filename)
                break
        else:
            logging.debug('no PR templates found')
        self.__prs = None

    def get_prs(self, branch_name: str) -> list[ghgql.PR]:
        if self.__prs is None:
            self.__prs = self._search_stack_prs()
        return self.__prs.get(branch_name, list[ghgql.PR]())

    def is_sync(self, remote_pr: ghgql.PR, record: Stack) -> bool:
        if not record.get_parent() or record.branch_name is None:
            return True
        for pr in self.get_prs(record.branch_name):
            parent = record.get_parent()
            if parent is None:
                continue
            if pr.number == remote_pr.number and remote_pr.base != parent.branch_name:
                logging.debug("remote PR base doesn't match: %s vs %s", remote_pr.base, parent.branch_name)
                return False
        return True

    @classmethod
    def unresolved(cls, pr: ghgql.PR) -> dict[ghgql.Author, list[ghgql.Comment]]:
        result = [thread for thread in pr.threads.data if not thread.resolved]

        def author_reacted(thread: ghgql.ReviewThread) -> bool:
            if not thread.comments.data:
                logging.debug('no comments?')
                return False
            for reaction in thread.comments.data[-1].reactions.data:
                if reaction.author.login == pr.author.login and reaction.content not in ['EYES', 'CONFUSED']:
                    return True
            return False

        def author_commented(thread: ghgql.ReviewThread) -> bool:
            return len(thread.comments.data) > 0 and thread.comments.data[-1].author.login == pr.author.login

        comments: dict[ghgql.Author, list[ghgql.Comment]] = {}
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
        unresolved: dict[ghgql.Author, list[ghgql.Comment]]
        change_requested: list[ghgql.Review]
        approved: list[ghgql.Review]
        in_sync: bool

    def pr_stats(self, record: Stack) -> dict[ghgql.PR, PRStats]:
        stats: dict[ghgql.PR, GH.PRStats] = {}
        if record.branch_name is None:
            return stats
        for pr in self.get_prs(record.branch_name):
            authors: dict[str, ghgql.Review] = {}
            for r in pr.reviews.data:
                authors[r.author.login] = r
            nr = GH.unresolved(pr)
            cr = [r for r in authors.values() if r.state == 'CHANGES_REQUESTED']
            approved = [r for r in authors.values() if r.state == 'APPROVED']
            sync = self.is_sync(pr, record)
            stats[pr] = GH.PRStats(nr, cr, approved, sync)
        return stats

    def _make_stack_comment(self, current_pr_number: int) -> str:
        md = [COMMENT_BEGIN, COMMENT_FIRST_LINE, '']
        for record in self.stack.traverse():
            if record.branch_name is None:
                continue
            prs = self.get_prs(record.branch_name)
            if prs:
                for pr in prs:
                    line = '  ' * record.depth + f'* **PR #{pr.number}**'
                    if pr.number == current_pr_number:
                        line += ' 👈'
                    md.append(line)
            else:
                md.append('  ' * record.depth + f'* [{record.branch_name}](../tree/{record.branch_name})')
        md.append(COMMENT_END)
        return '\n'.join(md)

    def _search_stack_prs(self) -> dict[str, list[ghgql.PR]]:
        prs = dict[str, list[ghgql.PR]]()
        for record in self.stack.traverse():
            if not record.get_parent() and record.branch_name is not None:
                prs[record.branch_name] = []

        heads = [
            record.branch_name
            for record in self.stack.traverse()
            if (record.get_parent() or not record.length()) and record.branch_name is not None
        ]
        for pr in ghgql.search_prs(self.token, self.owner, self.repository, heads):
            if pr.head not in prs:
                prs.update({pr.head: [pr]})
            else:
                prs[pr.head].append(pr)

        logging.debug('Query done.')
        return prs

    def update_dependencies(self, pr: ghgql.PR) -> bool:
        logging.debug('adding dependencies to pr #%s', pr.number)
        comment_md = self._make_stack_comment(pr.number)
        body = _patch_body(pr.body, comment_md)
        if not body:
            logging.debug('dependencies are up to date')
            return False
        body = json.dumps(body, ensure_ascii=False)
        ghgql.graphql(
            self.token,
            ghgql.make_update_pr_query(gql.input(pullRequestId=f'"{pr.id}"', body=body)),
        )
        return True

    def update_pr(self, record: Stack, pr: ghgql.PR) -> bool:
        parent = record.get_parent()
        if parent is None:
            return False
        base = parent.branch_name
        if base is None or pr.base == base:
            return False
        logging.debug('updating PR base from %s to %s', pr.base, base)
        ghgql.graphql(
            self.token,
            ghgql.make_update_pr_query(gql.input(pullRequestId=f'"{pr.id}"', baseRefName=f'"{base}"')),
        )
        pr.base = base
        return True

    def create_pr(self, base: str, branch_name: str, title: str = '', draft: bool = False) -> ghgql.PR:
        logging.debug('creating PR with base %s and head %s', base, branch_name)
        base_branch = self.repo.lookup_branch(base)
        if not base_branch.upstream:
            raise GhitError(f'Base branch {base} has no upstream.')
        repo_id_json = ghgql.graphql(
            self.token,
            ghgql.make_repo_id_query(owner=self.owner, repository=self.repository),
        )

        repository_id = repo_id_json['data']['repository']['id']
        head = f'{self.owner}:{branch_name}'
        title = json.dumps(title or branch_name, ensure_ascii=False)
        body = json.dumps(self.template, ensure_ascii=False)

        pr_json = ghgql.graphql(
            self.token,
            ghgql.make_create_pr_query(
                gql.input(
                    repositoryId=f'"{repository_id}"',
                    baseRefName=f'"{base}"',
                    headRefName=f'"{head}"',
                    title=title,
                    draft='true' if draft else 'false',
                    body=body,
                )
            ),
        )
        pr = ghgql.make_pr({'node': pr_json['data']['createPullRequest']['pullRequest']})
        if self.__prs is None:
            self.__prs = {}
        if branch_name in self.__prs:
            self.__prs[branch_name].append(pr)
        else:
            self.__prs.update({branch_name: [pr]})
        self.update_dependencies(pr)
        return pr


def init_gh(repo: git.Repository, stack: Stack, offline: bool) -> GH | None:
    gh = GH(repo, stack) if not offline and is_gh(repo) else None
    if gh:
        logging.debug('found gh repository %s', gh.repository)
    elif offline:
        logging.debug('working offline')
    else:
        logging.debug('gh not found')
    return gh
