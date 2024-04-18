from . import styling as s
from . import terminal
from .args import Args
from .common import check_record, connect, push_and_pr, rewrite_stack
from .error import GhitError


def check(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return

    insync = True
    for record in stack.traverse(False):
        insync = insync and check_record(repo, gh, record)

    if not insync:
        raise GhitError(s.warning('The stack is not in shape.'))


def stack_submit(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty or args.offline or not gh:
        return
    origin = repo.remotes['origin']
    if not origin:
        raise GhitError(s.warning('No origin found for the repository.'))

    prs = []
    needs_update = False
    for record in stack.traverse(False):
        branch_prs, pr_created = push_and_pr(repo, gh, origin, record)
        prs.extend(branch_prs)
        needs_update = needs_update or pr_created

    if needs_update and len(prs) > 1:
        # Update the ghit comments in all PRs except the last one, which doesn't
        # need to be updated, if a new PR has been created.
        for pr in prs[:-1]:
            gh.comment(pr)

def cleanup(args: Args) -> None:
    repo, stack, gh = connect(args)
    if repo.is_empty:
        return

    for record in stack.traverse(False):
        keep = repo.lookup_branch(record.branch_name) is not None
        if not args.offline and gh:
            keep = keep and all(pr.state != 'MERGED' for pr in gh.get_prs(record.branch_name))

        if not keep:
            record.disable()
            terminal.stdout(s.warning('Disabled'), s.emphasis(record.branch_name)+s.warning('.'))

    rewrite_stack(args.stack, repo, stack)
