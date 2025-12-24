import argparse
import logging

from . import branch_commands as bcom
from . import stack_commands as scom
from . import terminal
from . import top_commands as top
from .error import GhitError


def create_common_parser():
    """Create a parent parser with common arguments that can appear before or after commands."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('-r', '--repository', default='.', help='the git repository path (default .)')
    common.add_argument('-s', '--stack', help='the stack filename (default .ghit/stack)')
    common.add_argument('-o', '--offline', action='store_true', help='do not call GitHub')
    common.add_argument('-g', '--debug', action='store_true')
    common.add_argument('-v', '--verbose', action='store_true')
    return common


def add_top_commands(parser: argparse.ArgumentParser, common: argparse.ArgumentParser):
    commands = parser.add_subparsers(required=True)

    commands.add_parser(
        'init',
        help='create `.ghit/stack` file with the current branch',
        parents=[common],
    ).set_defaults(func=top.init)

    commands.add_parser(
        'ls',
        help='show the branches of stack with',
        parents=[common],
    ).set_defaults(func=top.ls)
    commands.add_parser(
        'up',
        help='check out one branch up the stack',
        parents=[common],
    ).set_defaults(func=top.up)
    commands.add_parser(
        'down', help='check out one branch down the stack', parents=[common]
    ).set_defaults(func=top.down)
    commands.add_parser(
        'top',
        help='check out the top of the stack',
        parents=[common],
    ).set_defaults(func=top.top)
    commands.add_parser(
        'bottom', help='check out the bottom of the stack', parents=[common]
    ).set_defaults(func=top.bottom)
    commands.add_parser('version', help='show program version', parents=[common]).set_defaults(func=top.version)

    return commands


def add_stack_commands(parser: argparse.ArgumentParser, common: argparse.ArgumentParser):
    parser_stack_sub = parser.add_subparsers()
    parser_stack_sub.add_parser('check', parents=[common]).set_defaults(func=scom.check)
    parser_stack_sub.add_parser(
        'submit',
        help='push stack branches upstream and update PRs',
        parents=[common],
    ).set_defaults(func=scom.stack_submit)
    parser_stack_sub.add_parser(
        'cleanup',
        help='removes unexisting branches from the stack, or the ones with merged PRs',
        parents=[common],
    ).set_defaults(func=scom.cleanup)
    parser_stack_sub.add_parser(
        'import',
        help="fetch user's open PRs from GitHub and append the branch tree to the stack",
        parents=[common],
    ).set_defaults(func=scom.import_prs)


def add_branch_commands(parser: argparse.ArgumentParser, common: argparse.ArgumentParser) -> None:
    parser_branch_sub = parser.add_subparsers()
    cr = parser_branch_sub.add_parser(
        'create', help='create branch, set remote upstream, update stack file', parents=[common]
    )
    cr.add_argument('branch', help='branch name to create')
    cr.set_defaults(func=bcom.create)

    upr = parser_branch_sub.add_parser(
        'submit',
        help='push branch upstream, create a PR or update the existing PR(s)',
        parents=[common],
    )
    upr.add_argument('-t', '--title', help='PR title')
    upr.add_argument('-d', '--draft', help='create draft PR', action='store_true')
    upr.set_defaults(func=bcom.branch_submit)

    parser_branch_sub.add_parser(
        'check', help='check the state of the branch and possible PRs', parents=[common]
    ).set_defaults(func=bcom.check)


def ghit(argv: list[str]) -> int:
    common = create_common_parser()
    parser = argparse.ArgumentParser(parents=[common])

    commands = add_top_commands(parser, common)
    add_stack_commands(commands.add_parser('stack', aliases=['s', 'st'], parents=[common]), common)
    add_branch_commands(commands.add_parser('branch', aliases=['b', 'br'], parents=[common]), common)

    args = parser.parse_args(args=argv)
    if 'func' not in args:
        parser.print_usage()
        terminal.stderr('Please provide the full command, with necessary subcommands.', args)
        return 1
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            args.func(args)
        except GhitError as br:
            msg = str(br)
            if msg:
                terminal.stderr(msg)
            return 1
    else:
        try:
            args.func(args)
        except GhitError as br:
            msg = str(br)
            if msg:
                terminal.stderr(msg)
            return 1
        except Exception as e:
            terminal.stderr('Error:', e)
            return 2
    return 0
