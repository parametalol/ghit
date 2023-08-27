import requests
from dataclasses import dataclass
import logging


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
        id
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
                id
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
                        id
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

GQL_ADD_COMMENT = """
mutation AddComment {{
  addComment(input: {{ subjectId: "{pr_id}", body: {body} }}) {{
    clientMutationId
  }}
}}"""

GQL_UPDATE_COMMENT = """
mutation UpdateComment {{
  updateIssueComment(input: {{ id: "{id}", body: {body} }}) {{
    clientMutationId
  }}
}}"""


# endregion query

# region classes


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
    id: str
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
    id: str
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


# endregion classes

# region constructors


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
        id=node["id"],
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


def make_pr(node: any) -> PR:
    return PR(
        number=node["number"],
        id=node["id"],
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


# endregion constructors


def graphql(token: str, query: str) -> any:
    response = requests.post(
        url=f"https://api.github.com/graphql",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"query": query},
    )
    logging.debug(f"response: {response}")
    if not response.ok:
        raise BaseException(response.text)
    return response.json()