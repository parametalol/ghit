import argparse
import logging
import os
import sys

from .branch_commands import branch_submit, create
from .common import Args, BadResult
from .stack_commands import check, stack_submit
from .top_commands import bottom, down, init, ls, top, up


def add_top_commands(parser: argparse.ArgumentParser):
    commands = parser.add_subparsers(required=True)

    commands.add_parser(
        "init",
        help="create `.ghit.stack` file with the current branch, "
        + "and add it to `.gitignore`",
    ).set_defaults(func=init)

    commands.add_parser(
        "ls",
        help="show the branches of stack with",
    ).set_defaults(func=ls)
    commands.add_parser(
        "up",
        help="check out one branch up the stack",
    ).set_defaults(func=up)
    commands.add_parser(
        "down", help="check out one branch down the stack"
    ).set_defaults(func=down)
    commands.add_parser(
        "top",
        help="check out the top of the stack",
    ).set_defaults(func=top)
    commands.add_parser(
        "bottom", help="check out the bottom of the stack"
    ).set_defaults(func=bottom)
    return commands


def add_stack_commands(parser: argparse.ArgumentParser):
    parser_stack_sub = parser.add_subparsers()
    parser_stack_sub.add_parser("check").set_defaults(func=check)
    # parser_stack_sub.add_parser(
    #    "restack",
    #    help="suggest git commands to rebase the branches "
    #    + "according to the stack",
    # ).set_defaults(func=restack)
    parser_stack_sub.add_parser(
        "submit",
        help="push stack branches upstream and update PRs",
    ).set_defaults(func=stack_submit)


def add_branch_commands(parser: argparse.ArgumentParser):
    parser_branch_sub = parser.add_subparsers()
    cr = parser_branch_sub.add_parser(
        "create", help="create branch, set remote upstream, update stack file"
    )
    cr.add_argument("branch", help="branch name to create")
    cr.set_defaults(func=create)

    upr = parser_branch_sub.add_parser(
        "submit",
        help="push branch upstream, create a PR or update the existing PR(s)",
    )
    upr.add_argument("-t", "--title", help="PR title")
    upr.add_argument(
        "-d", "--draft", help="create draft PR", action="store_true"
    )
    upr.set_defaults(func=branch_submit)


def ghit(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--repository", default=".")
    parser.add_argument(
        "-s", "--stack", default=os.getenv("GHIT_STACK") or ".ghit.stack"
    )
    parser.add_argument("-o", "--offline", action="store_true")
    parser.add_argument("-g", "--debug", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")

    commands = add_top_commands(parser)
    add_stack_commands(commands.add_parser("stack", aliases=["s", "st"]))
    add_branch_commands(commands.add_parser("branch", aliases=["b", "br"]))

    args: Args = parser.parse_args(args=argv)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            args.func(args)
        except BadResult as br:
            if br.message:
                print(br.message, file=sys.stderr)
            return 1
    else:
        try:
            args.func(args)
        except BadResult as br:
            if br.message:
                print(br.message, file=sys.stderr)
            return 1
        except Exception as e:
            print("Error:", e)
            return 2
    return 0
