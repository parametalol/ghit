from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .error import GhitError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class Stack:
    def __init__(
        self,
        branch_name: str | None = None,
        enabled: bool = False,
        parent: Stack | None = None,
        in_stack: bool = True
    ):
        self.branch_name = branch_name
        self.__parent = parent
        self._enabled = enabled
        self._in_stack = in_stack
        self.depth = parent.depth + 1 if parent else -1
        self._index = parent.length() if parent else 0
        self._children = dict[str, Stack]()

    def get_parent(self, ignore_enabled: bool = False) -> Stack | None:
        if self.__parent is None:
            return None
        p = self.__parent
        return p if p._enabled or ignore_enabled else p.get_parent(ignore_enabled)

    def disable(self) -> None:
        self._enabled = False

    def add_child(self, branch_name: str, enabled: bool = True, in_stack: bool = True) -> Stack:
        if branch_name in self._children:
            raise GhitError(f"'{branch_name}' already exist in '{self.branch_name}'")
        child = Stack(branch_name, enabled, self, in_stack)
        self._children.update({branch_name: child})
        return child

    def is_last_child(self) -> bool:
        parent = self.get_parent()
        return self.is_root() or parent is not None and self._index == parent.length() - 1

    def is_in_stack(self) -> bool:
        return self._in_stack

    def length(self) -> int:
        # Skip disabled children
        length = 0
        for v in self._children.values():
            if v._enabled:
                length += 1
            else:
                length += v.length()
        return length

    def is_root(self) -> bool:
        return self.branch_name is None

    def traverse(self, with_first_level: bool = True, ignored_disabled: bool = False) -> Iterator[Stack]:
        if not self.is_root() and (self._enabled or ignored_disabled) and \
            (self.get_parent(ignored_disabled) or with_first_level):
            yield self
        for r in self._children.values():
            yield from r.traverse(with_first_level, ignored_disabled)

    def find(self, branch_name: str) -> Stack | None:
        for s in self.traverse(True, True):
            if s.branch_name == branch_name:
                return s
        return None

    def _find_depth(self) -> int:
        depth = 0
        for record in self.traverse():
            depth = max(depth, record.depth)
        return depth

    def rtraverse(self, with_first_level: bool = True) -> Iterator[Stack]:
        depth = self._find_depth()
        while depth:
            for record in self.traverse(with_first_level):
                if record.depth == depth:
                    yield record
            depth -= 1

    def dumps(self, lines: list[str] | None = None, depth: int = 0) -> list[str]:
        if lines is None:
            lines = []
        if not self.is_root():
            lines.append(('' if self._enabled else '#') + '.' * depth + self.branch_name) # type: ignore
        for record in self._children.values():
            record.dumps(lines, depth + (not self.is_root()))
        return lines


def parse_line(line: str, parents: list[Stack]) -> Stack | None:
    line = line.strip(' \t\r\n')
    enabled = not line.startswith('#')
    stack_line = line.lstrip('#').lstrip()
    branch_name = stack_line.lstrip('. \t')
    if not branch_name:
        return None

    depth = 0
    while stack_line[depth] == '.':
        depth += 1

    while True:
        parent = parents[-1] if parents else None
        if parent is None or not parent.branch_name or parent.depth < depth:
            break
        parents.pop()

    if parent is None or enabled and depth - parent.depth > 1:
        raise GhitError('bad indent')

    logging.debug('parsed: %s%s%s parent: %s', '' if enabled else '#', '.'*depth, branch_name, parent.branch_name)

    child = parent.add_child(branch_name, enabled)
    parents.append(child)
    return child


def parse(lines: list[str] | Iterator[str]) -> Stack:
    stack = Stack()
    parents = [stack]
    for i, line in enumerate(lines, start=1):
        logging.debug('reading line [%s]', line)
        try:
            parse_line(line, parents)
        except GhitError as e:
            raise GhitError(f'line {i}: {e}') from e
    return stack


def open_stack(filename: Path | None) -> Stack | None:
    if filename is None or not filename.is_file():
        return None
    with filename.open() as f:
        return parse(f.readlines())
