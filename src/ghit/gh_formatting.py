from __future__ import annotations

from typing import TYPE_CHECKING

from . import styling as s

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from datetime import datetime

    from .gh import GH
    from .gh_graphql import PR, Author, Comment, Review
    from .stack import Stack

# region style

pr_state_style: dict[str, Callable[[str], str]] = {
    'OPEN': s.good,
    'CLOSED': lambda m: s.danger(s.deleted(m)),
    'MERGED': s.calm,
    'DRAFT': s.inactive,
}


def _pr_state_style(pr: PR) -> Callable[[str], str]:
    return pr_state_style['DRAFT' if pr.draft else str(pr.state).upper()]


def pr_number_with_style(pr: PR) -> str:
    number = s.with_style('dim', _pr_state_style(pr)(f'#{pr.number} ({pr.state})'))
    return ('🔒' if pr.locked else '') + s.url(number, pr.url)


def pr_title_with_style(pr: PR) -> str:
    return s.with_style('dim', _pr_state_style(pr)(pr.title))


# endregion style


def format_info(gh: GH, verbose: bool, record: Stack, pr: PR, stats: GH.PRStats) -> Iterator[str]:
    pr_state = []
    if not verbose:
        if stats.unresolved:
            pr_state.append(s.warning('!'))
        if stats.change_requested:
            pr_state.append(s.danger('✗'))
        elif stats.approved:
            pr_state.append(s.good('✓'))
        if not stats.in_sync:
            pr_state.append(s.warning('⟳'))

    yield ''.join(
        [
            pr_number_with_style(pr),
            *pr_state,
            ' ',
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
        yield s.with_style('dim', s.good('✓ Approved by ')) + s.with_style(
            'italic', s.good(str(r.author))
        ) + s.with_style('dim', s.good('.'))


def _format_not_sync(gh: GH, record: Stack, pr: PR) -> Iterator[str]:
    if not record.get_parent() or record.branch_name is None:
        return
    for p in gh.get_prs(record.branch_name):
        parent = record.get_parent()
        if parent is None:
            continue
        if p.number == pr.number and p.base != parent.branch_name:
            yield s.with_style(
                'dim',
                s.warning('⟳ PR base ')
                + s.emphasis(p.base)
                + s.warning(" doesn't match branch parent ")
                + s.emphasis(parent.branch_name or '<empty>')
                + s.warning('.'),
            )


def _format_change_requested(
    change_requested: list[Review],
) -> Iterator[str]:
    for review in change_requested:
        yield s.with_style('dim', s.danger('✗ Changes requested by ')) + s.with_style(
            'italic', s.danger(str(review.author))
        ) + s.with_style('dim', s.danger(':'))

        yield f'  {s.colorful(review.url)}'


def _late_commment_sign(comment: Comment, merged_at: datetime | None) -> str:
    return '' if not merged_at or merged_at > comment.created_at else s.warning('+ ')


def _format_not_resolved(nr: dict[Author, list[Comment]], merged_at: datetime | None) -> Iterator[str]:
    for author, comments in nr.items():
        if len(comments) == 1:
            yield s.with_style(
                'dim',
                s.warning('! No reaction to a comment by '),
            ) + s.with_style(
                'italic', s.warning(str(author))
            ) + s.with_style('dim', s.warning(':'))
            yield '  ' + _late_commment_sign(comments[0], merged_at) + s.colorful(comments[0].url)

        else:
            yield s.with_style(
                'dim',
                s.warning('! No reaction to comments by '),
            ) + s.with_style(
                'italic', s.warning(str(author))
            ) + s.with_style('dim', s.warning(':'))

            for i, comment in enumerate(comments, start=1):
                yield '  ' + s.warning(f'{i}. ') + _late_commment_sign(comment, merged_at) + s.colorful(comment.url)
