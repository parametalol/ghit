#!/usr/bin/env python3

import os
import argparse
import logging

from .common import *
from .gitools import *
from .styling import *
from .top_commands import ls, up, down, top, bottom
from .stack_commands import check, restack, stack_sync, get_comments
from .pr_commands import update_pr, pr_sync

def add_top_commands(parser: argparse.ArgumentParser):
    commands = parser.add_subparsers(required=True)

    commands.add_parser("ls", help="show the branches of stack with").set_defaults(
        func=ls
    )
    commands.add_parser("up", help="check out one branch up the stack").set_defaults(
        func=up
    )
    commands.add_parser(
        "down", help="check out one branch down the stack"
    ).set_defaults(func=down)
    commands.add_parser("top", help="check out the top of the stack").set_defaults(
        func=top
    )
    commands.add_parser(
        "bottom", help="check out the bottom of the stack"
    ).set_defaults(func=bottom)
    return commands

def add_stack_commands(parser: argparse.ArgumentParser):
    parser_stack_sub = parser.add_subparsers()
    parser_stack_sub.add_parser("check").set_defaults(func=check)
    parser_stack_sub.add_parser("comments").set_defaults(func=get_comments)
    parser_stack_sub.add_parser(
        "restack",
        help="suggest git commands to rebase the branches according to the stack",
    ).set_defaults(func=restack)
    parser_stack_sub.add_parser(
        "sync", help="fetch from origin and push stack branches upstream"
    ).set_defaults(func=stack_sync)

def add_pr_commands(parser: argparse.ArgumentParser):
    parser_pr_sub = parser.add_subparsers()
    upr = parser_pr_sub.add_parser(
        "update",
        help="create new draft PR or update the existing PR opened from the current branch",
    )
    upr.add_argument("-t", "--title", help="PR title")
    upr.set_defaults(func=update_pr)
    parser_pr_sub.add_parser(
        "sync", help="creates or updates PRs of the stack"
    ).set_defaults(func=pr_sync)

def ghit(argv: list[str]):
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
    add_pr_commands(commands.add_parser("pr"))

    args: Args = parser.parse_args(args=argv)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.debug:
        args.func(args)
    else:
        try:
            args.func(args)
        except Exception as e:
            print("Error:", e)
