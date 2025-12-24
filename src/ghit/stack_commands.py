from . import gh_graphql as ghgql
from . import styling as s
from . import terminal
from . import top_commands as top
from .args import Args
from .common import check_record, connect, push_and_pr, rewrite_stack
from .error import GhitError
from .gitools import get_current_branch
from .stack import Stack


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
        # Update the deps section in all PRs except the last one, which doesn't
        # need to be updated, if a new PR has been created.
        for pr in prs[:-1]:
            gh.update_dependencies(pr)

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


def _build_pr_tree(
    prs: list[ghgql.SimplePR],
    stack: Stack,
) -> None:
    """Build a branch tree from PRs and add to stack."""
    heads = {pr.head for pr in prs}
    bases = {pr.base for pr in prs}
    roots = bases - heads

    # Build adjacency: base -> list of head branches
    children: dict[str, list[str]] = {}
    for pr in prs:
        children.setdefault(pr.base, []).append(pr.head)

    def add_branch_tree(parent: Stack, branch: str) -> None:
        node = stack.find(branch) or parent.add_child(branch)
        for child in children.get(branch, []):
            add_branch_tree(node, child)

    for root in sorted(roots):
        root_node = stack.find(root) or stack.add_child(root)
        for child in children.get(root, []):
            add_branch_tree(root_node, child)


def _print_stack_ls(args: Args, repo, stack: Stack, gh) -> None:
    """Print the stack in the same format as `ghit ls`."""
    checked_out = get_current_branch(repo).branch_name
    parent_prefix: list[str] = []

    for record in stack.traverse():
        parent_prefix = parent_prefix[: max(record.depth - 1, 0)]
        top._print_line(repo, record.branch_name == checked_out, parent_prefix, record)
        if record.get_parent():
            parent_prefix.append(top._parent_tab(record))
        top._print_gh_info(args.verbose, gh, parent_prefix, record)


def import_prs(args: Args) -> None:
    """Fetch user's open PRs from GitHub and append the branch tree to the stack."""
    repo, stack, gh = connect(args)
    if repo.is_empty:
        raise GhitError(s.danger('Repository is empty.'))
    if args.offline or not gh:
        raise GhitError(s.danger('Cannot import PRs in offline mode.'))

    prs = ghgql.search_user_open_prs(gh.token, gh.owner, gh.repository)
    if not prs:
        terminal.stdout(s.warning('No open PRs found for the current user.'))
        return

    _build_pr_tree(prs, stack)
    rewrite_stack(args.stack, repo, stack)
    _print_stack_ls(args, repo, stack, gh)
