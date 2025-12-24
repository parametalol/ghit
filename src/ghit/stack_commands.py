from . import gh_graphql as ghgql
from . import styling as s
from . import terminal
from . import top_commands as top
from .args import Args
from .common import Context, check_record, connect, push_and_pr, rewrite_stack
from .error import GhitError
from .gitools import get_current_branch
from .stack import Stack


def check(args: Args) -> None:
    ctx = connect(args)
    if ctx.is_empty:
        return

    insync = True
    for record in ctx.stack.traverse(False):
        insync = insync and check_record(ctx, record)

    if not insync:
        raise GhitError(s.warning('The stack is not in shape.'))


def stack_submit(args: Args) -> None:
    ctx = connect(args)
    if ctx.is_empty or ctx.offline or not ctx.gh:
        return
    origin = ctx.repo.remotes['origin']
    if not origin:
        raise GhitError(s.warning('No origin found for the repository.'))

    prs = []
    needs_update = False
    for record in ctx.stack.traverse(False):
        branch_prs, pr_created = push_and_pr(ctx, origin, record)
        prs.extend(branch_prs)
        needs_update = needs_update or pr_created

    if needs_update and len(prs) > 1:
        # Update the deps section in all PRs except the last one, which doesn't
        # need to be updated, if a new PR has been created.
        for pr in prs[:-1]:
            ctx.gh.update_dependencies(pr)


def cleanup(args: Args) -> None:
    ctx = connect(args)
    if ctx.is_empty:
        return

    for record in ctx.stack.traverse(False):
        keep = ctx.repo.lookup_branch(record.branch_name) is not None
        if not ctx.offline and ctx.gh:
            keep = keep and all(pr.state != 'MERGED' for pr in ctx.gh.get_prs(record.branch_name))

        if not keep:
            record.disable()
            terminal.stdout(s.warning('Disabled'), s.emphasis(record.branch_name)+s.warning('.'))

    rewrite_stack(ctx)


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


def _print_stack_ls(ctx: Context) -> None:
    """Print the stack in the same format as `ghit ls`."""
    checked_out = get_current_branch(ctx.repo).branch_name
    parent_prefix: list[str] = []

    for record in ctx.stack.traverse():
        parent_prefix = parent_prefix[: max(record.depth - 1, 0)]
        top._print_line(ctx.repo, record.branch_name == checked_out, parent_prefix, record)
        if record.get_parent():
            parent_prefix.append(top._parent_tab(record))
        top._print_gh_info(ctx.verbose, ctx.gh, parent_prefix, record)


def import_prs(args: Args) -> None:
    """Fetch user's open PRs from GitHub and append the branch tree to the stack."""
    ctx = connect(args)
    if ctx.is_empty:
        raise GhitError(s.danger('Repository is empty.'))
    if ctx.offline or not ctx.gh:
        raise GhitError(s.danger('Cannot import PRs in offline mode.'))

    prs = ghgql.search_user_open_prs(ctx.gh.token, ctx.gh.owner, ctx.gh.repository)
    if not prs:
        terminal.stdout(s.warning('No open PRs found for the current user.'))
        return

    _build_pr_tree(prs, ctx.stack)
    rewrite_stack(ctx)
    _print_stack_ls(ctx)
