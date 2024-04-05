from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import requests

from . import graphql as gql
from . import terminal

# region query

FIRST_FEW = {'first': 10}

GQL_REACTION = gql.fields('content', gql.obj('user', 'login', 'name'))
GQL_AUTHOR = gql.obj('author', 'login', gql.on('User', 'name'))
GQL_COMMENT = gql.fields(
    'id',
    'url',
    'body',
    'createdAt',
    GQL_AUTHOR,
    gql.paged('reactions', FIRST_FEW, GQL_REACTION),
)
GQL_REVIEW_THREAD = gql.fields(
    'path',
    'isResolved',
    'isOutdated',
    gql.paged('comments', {'last': 1}, GQL_COMMENT),
)
GQL_REVIEW = gql.fields('state', 'url', GQL_AUTHOR)
GQL_COMMIT = gql.obj('commit', gql.paged('comments', {'last': 1}, GQL_COMMENT))
GQL_PR = gql.fields(
    'number',
    'id',
    'title',
    GQL_AUTHOR,
    'url',
    'baseRefName',
    'headRefName',
    'isDraft',
    'locked',
    'closed',
    'merged',
    'mergedAt',
    'state',
    gql.paged('comments', FIRST_FEW, GQL_COMMENT),
    gql.paged('reviewThreads', FIRST_FEW, GQL_REVIEW_THREAD),
    gql.paged('reviews', FIRST_FEW, GQL_REVIEW),
    gql.paged('commits', FIRST_FEW, GQL_COMMIT),
)


def first_n_after(name: str, q: str, n: int, after: str, **opts):
    return gql.paged(name, {'first': n, 'after': gql.cursor_or_null(after), **opts}, q)


def make_prs_query(owner: str, repository: str, heads: list[str], after: str | None = None):
    return gql.query(
        'query search_prs',
        first_n_after(
            'search',
            gql.on('PullRequest', GQL_PR),
            10,
            after,
            type='ISSUE',
            query=f'"repo:{owner}/{repository} is:pr {heads}"',
        ),
    )


def pr_details_query(name: str, detail: Callable[..., str]):
    def q(owner: str, repository: str, pr_number: int, *after: str):
        return gql.query(
            f'query {name}',
            gql.func(
                'repository',
                {'owner': f'"{owner}"', 'name': f'"{repository}"'},
                gql.func('pullRequest', {'number': pr_number}, detail(*after)),
            ),
        )

    return q


GQL_PR_COMMENTS_QUERY = pr_details_query(
    'pr_comments',
    lambda after: first_n_after(
        'comments',
        GQL_COMMENT,
        10,
        after,
    ),
)

GQL_PR_COMMENT_REACTIONS_QUERY = pr_details_query(
    'pr_comments_reactions',
    lambda comment_cursor, after: first_n_after(
        'comments',
        first_n_after('reactions', GQL_REACTION, 10, after),
        1,
        comment_cursor,
    ),
)

GQL_PR_THREADS_QUERY = pr_details_query(
    'pr_reviewThreads',
    lambda after: first_n_after('reviewThreads', GQL_REVIEW_THREAD, 40, after),
)

GQL_PR_THREAD_COMMENTS_QUERY = pr_details_query(
    'pr_thread_comments',
    lambda thread_cursor, comment_cursor, after: first_n_after(
        'reviewThreads',
        first_n_after(
            'comments',
            first_n_after('reactions', GQL_REACTION, 10, after),
            1,
            comment_cursor,
        ),
        1,
        thread_cursor,
    ),
)

GQL_PR_COMMITS_QUERY = pr_details_query('pr_commits', lambda after: first_n_after('commits', GQL_COMMIT, 10, after))

GQL_PR_COMMIT_COMMENTS_QUERY = pr_details_query(
    'pr_threads_comments',
    lambda commit_cursor, after: first_n_after(
        'commits',
        first_n_after('comments', GQL_COMMENT, 10, after),
        1,
        commit_cursor,
    ),
)

GQL_PR_COMMIT_COMMENT_REACTIONS_QUERY = pr_details_query(
    'pr_threads_comments',
    lambda commit_cursor, comment_cursor, after: first_n_after(
        'commits',
        first_n_after(
            'comments',
            first_n_after('reactions', GQL_REACTION, 10, after),
            1,
            comment_cursor,
        ),
        1,
        commit_cursor,
    ),
)

GQL_PR_REVIEWS_QUERY = pr_details_query('pr_reviews', lambda after: first_n_after('reviews', GQL_REVIEW, 40, after))


def make_repo_id_query(owner: str, repository: str) -> str:
    return gql.query(
        'query get_repo_id',
        gql.func(
            'repository',
            {'owner': f'"{owner}"', 'name': f'"{repository}"'},
            'id',
        ),
    )


# endregion query

# region mutations


def make_add_comment_query(comment_input: any) -> str:
    return gql.query(
        'mutation add_pr_comment',
        gql.func('addComment', comment_input, 'clientMutationId'),
    )


def make_update_comment_query(comment_input: any) -> str:
    return gql.query(
        'mutation update_pr_comment',
        gql.func('updateIssueComment', comment_input, 'clientMutationId'),
    )


def make_create_pr_query(pr_input: any) -> str:
    return gql.query(
        'mutation create_pr',
        gql.func(
            'createPullRequest',
            pr_input,
            'clientMutationId',
            gql.obj('pullRequest', GQL_PR),
        ),
    )


def make_update_pr_base_query(pr_input: any) -> str:
    return gql.query(
        'mutation update_pr',
        gql.func(
            'updatePullRequest',
            pr_input,
            'clientMutationId',
        ),
    )


# endregion mutations

# region classes


@dataclass
class Author:
    login: str
    name: str | None

    def __str__(self) -> str:
        if self.name and self.login:
            return f'{self.name} ({self.login})'
        return self.name or self.login

    def __hash__(self) -> int:
        return hash(self.login)


@dataclass
class Reaction:
    content: str
    author: Author


@dataclass
class Comment:
    id: str
    author: Author
    created_at: datetime
    body: str
    reacted: bool
    url: str
    reactions: gql.Pages[Reaction]
    cursor: str


@dataclass
class ReviewThread:
    path: str
    resolved: bool
    outdated: bool
    comments: gql.Pages[Comment]
    cursor: str


@dataclass
class Review:
    author: Author
    state: str
    url: str


@dataclass
class Commit:
    comments: gql.Pages[Comment]
    cursor: str


@dataclass
class PR:
    number: int
    id: str
    author: Author
    title: str
    url: str
    state: str
    closed: bool
    merged: bool
    merged_at: datetime | None
    locked: bool
    draft: bool
    base: str
    head: str
    threads: gql.Pages[ReviewThread]
    comments: gql.Pages[Comment]
    reviews: gql.Pages[Review]
    commits: gql.Pages[Commit]

    def __hash__(self) -> int:
        return self.number


# endregion classes

# region constructors


def _make_author(obj: any) -> Author:
    return Author(
        login=obj['login'],
        name=gql.path(obj, 'name'),
    )


def _make_reaction(edge: any) -> Reaction:
    node = edge['node']
    return Reaction(
        content=node['content'],
        author=_make_author(node['user']),
    )


def query_reactions(subject: str, args: dict[str, any]) -> str:
    return gql.query('query reactions', gql.func(subject, args, GQL_REACTION))


def query_pr_comments(owner: str, repository: str, pr: int) -> str:
    return gql.query(
        'query pr_comments',
        gql.func(
            'repository',
            {'owner': f'"{owner}"', 'name': f'"{repository}"'},
            gql.func('pullRequest', {'id': pr}),
            GQL_COMMENT,
        ),
    )


def _make_comment(edge: any) -> Comment:
    node = edge['node']
    return Comment(
        id=node['id'],
        author=_make_author(node['author']),
        created_at=datetime.fromisoformat(node['createdAt']),
        body=node['body'],
        reacted=False,
        url=node['url'],
        reactions=gql.Pages('reactions', _make_reaction, node),
        cursor=edge['cursor'],
    )


def _make_review(edge: any) -> Review:
    node = edge['node']
    return Review(
        author=_make_author(node['author']),
        state=node['state'],
        url=node['url'],
    )


def _make_commit(edge: any) -> Commit:
    node = edge['node']
    return Commit(
        comments=gql.Pages('comments', _make_comment, node),
        cursor=edge['cursor'],
    )


def _make_thread(edge: any) -> ReviewThread:
    node = edge['node']
    return ReviewThread(
        path=node['path'],
        resolved=node['isResolved'],
        outdated=node['isOutdated'],
        comments=gql.Pages('comments', _make_comment, node),
        cursor=edge['cursor'],
    )


def make_pr(edge: any) -> PR:
    node = edge['node']
    return PR(
        number=node['number'],
        id=node['id'],
        author=_make_author(node['author']),
        title=node['title'],
        url=node['url'],
        draft=node['isDraft'],
        locked=node['locked'],
        closed=node['closed'],
        merged=node['merged'],
        merged_at=datetime.fromisoformat(node['mergedAt']) if node['merged'] else None,
        state=node['state'],
        base=node['baseRefName'],
        head=node['headRefName'],
        comments=gql.Pages('comments', _make_comment, node),
        threads=gql.Pages('reviewThreads', _make_thread, node),
        reviews=gql.Pages('reviews', _make_review, node),
        commits=gql.Pages('commits', _make_commit, node),
    )


# endregion constructors


def graphql(token: str, query: str) -> any:
    logging.debug('query GH graphql: %s', query)
    response = requests.post(
        url=os.getenv('GITHUB_API_URL', 'https://api.github.com/graphql'),
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github.v3+json',
        },
        json={'query': query},
        timeout=30,
    )
    logging.debug('response: %s', response.status_code)
    if not response.ok:
        raise BaseException(response.text)
    result = response.json()
    logging.debug('response json: %s', result)
    if 'errors' in result:
        for error in result['errors']:
            if 'type' in error:
                terminal.stderr(f"{error['type']}: {error['message']}")
            else:
                terminal.stderr(error['message'])

        raise BaseException('errors in GraphQL response')
    return result


def search_prs(token: str, owner: str, repository: str, branches: list[str] = None) -> list[PR]:
    if branches is None:
        branches = []
    if not branches:
        return []

    heads = ' '.join(f'head:{branch}' for branch in branches)

    prs_pages = gql.Pages('search', make_pr)
    prs_pages.append_all(
        lambda after: gql.path(
            graphql(token, make_prs_query(owner, repository, heads, after)),
            'data',
        )
    )
    prs = prs_pages.data
    pr_path = ['data', 'repository', 'pullRequest']
    for pr in prs:
        _fetch_level_one(token, owner, repository, pr_path, pr)
    for pr in prs:
        _fetch_level_two(token, owner, repository, pr_path, pr)
    for pr in prs:
        _fetch_level_three(token, owner, repository, pr_path, pr)
    return prs


def _fetch_level_one(token: str, owner: str, repository: str, pr_path: list[str], pr: PR):
    pr.comments.append_all(
        lambda after: gql.path(
            graphql(
                token,
                GQL_PR_COMMENTS_QUERY(owner, repository, pr.number, after),
            ),
            *pr_path,
        )
    )
    pr.threads.append_all(
        lambda after: gql.path(
            graphql(
                token,
                GQL_PR_THREADS_QUERY(owner, repository, pr.number, after),
            ),
            *pr_path,
        )
    )
    pr.reviews.append_all(
        lambda after: gql.path(
            graphql(
                token,
                GQL_PR_REVIEWS_QUERY(owner, repository, pr.number, after),
            ),
            *pr_path,
        )
    )
    pr.commits.append_all(
        lambda after: gql.path(
            graphql(
                token,
                GQL_PR_COMMITS_QUERY(owner, repository, pr.number, after),
            ),
            *pr_path,
        )
    )


def _fetch_level_two(token: str, owner: str, repository: str, pr_path: list[str], pr: PR):
    for comment in pr.comments.data:
        comment.reactions.append_all(
            lambda after, cc=comment.cursor: gql.path(
                graphql(
                    token,
                    GQL_PR_COMMENT_REACTIONS_QUERY(owner, repository, pr.number, cc, after),
                    *pr_path,
                    'comments',
                )
            )
        )
    for thread in pr.threads.data:
        thread.comments.append_all(
            lambda after, tc=thread.cursor: gql.path(
                graphql(
                    token,
                    GQL_PR_THREAD_COMMENTS_QUERY(owner, repository, pr.number, tc, after),
                ),
                *pr_path,
                'reviewThreads',
                'edges',
                0,
                'node',
                'comments',
            )
        )
    for commit in pr.commits.data:
        commit.comments.append_all(
            lambda after: gql.path(
                graphql(
                    token,
                    GQL_PR_COMMIT_COMMENTS_QUERY(owner, repository, pr.number, after),
                ),
                *pr_path,
                'commits',
                'edges',
                0,
                'node',
                'comments',
            ),
        )


def _fetch_level_three(token: str, owner: str, repository: str, pr_path: list[str], pr: PR):
    for thread in pr.threads.data:
        for comment in thread.comments.data:
            comment.reactions.append_all(
                lambda after, cc=comment.cursor: gql.path(
                    graphql(
                        token,
                        GQL_PR_COMMENT_REACTIONS_QUERY(owner, repository, pr.number, cc, after),
                    ),
                    *pr_path,
                    'comments',
                    'edges',
                    0,
                    'reactions',
                )
            )
    for commit in pr.commits.data:
        for comment in commit.comments.data:
            comment.reactions.append_all(
                lambda after, cic=commit.cursor, coc=comment.cursor: gql.path(
                    graphql(
                        token,
                        GQL_PR_COMMIT_COMMENT_REACTIONS_QUERY(
                            owner,
                            repository,
                            pr.number,
                            cic,
                            coc,
                            after,
                        ),
                    ),
                    *pr_path,
                    'commits',
                    'edges',
                    0,
                    'comments',
                    'edges',
                    0,
                    'reactions',
                )
            )
