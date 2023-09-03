from collections.abc import Iterator, Callable
from datetime import datetime
from .gh_graphql import PR, Review, Author, Comment
from .stack import Stack
from .styling import (
    good,
    calm,
    inactive,
    danger,
    deleted,
    warning,
    emphasis,
    colorful,
    with_style,
)
from .gh import GH


# region style

pr_state_style: dict[str, Callable[[str], str]] = {
    "OPEN": good,
    "CLOSED": lambda m: danger(deleted(m)),
    "MERGED": calm,
    "DRAFT": inactive,
}


def _pr_state_style(pr: PR) -> Callable[[str], str]:
    return pr_state_style["DRAFT" if pr.draft else str(pr.state).upper()]


def pr_number_with_style(pr: PR) -> str:
    number = with_style(
        "dim", _pr_state_style(pr)(f"#{pr.number} ({pr.state})")
    )
    return ("🔒" if pr.locked else "") + number


def pr_title_with_style(pr: PR) -> str:
    return with_style("dim", _pr_state_style(pr)(pr.title))


# endregion style


def format_info(
    gh: GH, verbose: bool, record: Stack, pr: PR, stats: GH.PRStats
) -> Iterator[str]:
    pr_state = []
    if not verbose:
        if stats.unresolved:
            pr_state.append(warning("!"))
        if stats.change_requested:
            pr_state.append(danger("✗"))
        elif stats.approved:
            pr_state.append(good("✓"))
        if not stats.in_sync:
            pr_state.append(warning("⟳"))

    yield "".join(
        [
            pr_number_with_style(pr),
            *pr_state,
            " ",
            pr_title_with_style(pr),
        ]
    )

    if verbose:
        yield from _format_approved(stats.approved)
        if not stats.in_sync:
            yield from _format_not_sync(gh, record, pr)
        if stats.unresolved:
            yield from _format_not_resolved(stats.unresolved, pr.merged_at)
        if stats.change_requested:
            yield from _format_change_requested(stats.change_requested)


def _format_approved(approved: list[Review]) -> Iterator[str]:
    for r in approved:
        yield with_style("dim", good("✓ Approved by ")) + with_style(
            "italic", good(str(r.author))
        ) + with_style("dim", good("."))


def _format_not_sync(gh: GH, record: Stack, pr: PR) -> Iterator[str]:
    if not record.get_parent():
        return
    for p in gh.getPRs(record.branch_name):
        if p.number == pr.number:
            if p.base != record.get_parent().branch_name:
                yield with_style(
                    "dim",
                    warning("⟳ PR base ")
                    + emphasis(p.base)
                    + warning(" doesn't match branch parent ")
                    + emphasis(record.get_parent().branch_name)
                    + warning("."),
                )


def _format_change_requested(
    change_requested: list[Review],
) -> Iterator[str]:
    for review in change_requested:
        yield with_style(
            "dim", danger("✗ Changes requested by ")
        ) + with_style("italic", danger(str(review.author))) + with_style(
            "dim", danger(":")
        )

        yield f"  {colorful(review.url)}"


def _late_commment_sign(comment: Comment, merged_at: datetime | None) -> str:
    return (
        ""
        if not merged_at or merged_at > comment.created_at
        else warning("+ ")
    )


def _format_not_resolved(
    nr: dict[Author, list[Comment]], merged_at: datetime | None
) -> Iterator[str]:
    for author, comments in nr.items():
        if len(comments) == 1:
            yield with_style(
                "dim",
                warning("! No reaction to a comment by "),
            ) + with_style("italic", warning(str(author))) + with_style(
                "dim", warning(":")
            )
            yield "  " + _late_commment_sign(
                comments[0], merged_at
            ) + colorful(comments[0].url)

        else:
            yield with_style(
                "dim",
                warning("! No reaction to comments by "),
            ) + with_style("italic", warning(str(author))) + with_style(
                "dim", warning(":")
            )

            for i, comment in enumerate(comments, start=1):
                yield "  " + warning(f"{i}. ") + _late_commment_sign(
                    comment, merged_at
                ) + colorful(comment.url)
