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
    ):
        self.branch_name = branch_name
        self.__parent = parent
        self._enabled = enabled
        self.depth = parent.depth + 1 if parent else 0
        self._index = parent.length() if parent else 0
        self._children = dict[str, Stack]()

    def get_parent(self) -> Stack:
        if self.__parent is None:
            return None
        p = self.__parent
        return p if p._enabled else p.get_parent()

    def disable(self) -> None:
        self._enabled = False

    def add_child(self, branch_name: str, enabled: bool = True) -> Stack:
        if branch_name in self._children:
            raise GhitError(f"'{branch_name}' already exist in '{self.branch_name}'")
        child = Stack(branch_name, enabled, self if self._enabled else self.get_parent())
        self._children.update({branch_name: child})
        return child

    def is_last_child(self) -> bool:
        return self.is_root() or self._index == self.get_parent().length() - 1

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

    def traverse(self, with_first_level: bool = True) -> Iterator[Stack]:
        if not self.is_root() and self._enabled and (self.get_parent() or with_first_level):
            yield self
        for r in self._children.values():
            yield from r.traverse(with_first_level)

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

    def dumps(self, lines: list[str] = None, depth: int = 0) -> list[str]:
        if lines is None:
            lines = []
        if not self.is_root():
            lines.append(('' if self._enabled else '#') + '.' * depth + self.branch_name)
        for record in self._children.values():
            record.dumps(lines, depth + (not self.is_root()))
        return lines


def parse_line(line: str, parents: list[Stack]) -> Stack:
    enabled = not line.startswith('#')

    stack_line = line.rstrip().lstrip('#')
    branch_name = stack_line.lstrip('.')
    if not branch_name:
        raise GhitError('no branch name')

    depth = len(stack_line) - len(branch_name)

    if len(parents) <= depth:
        raise GhitError('bad indent')

    for _ in range(1, len(parents) - depth):
        parents.pop()

    parent = parents[-1]
    depth = min(depth, parent.depth + 1)

    logging.debug('parsed: %s%s%s parent: %s', '' if enabled else '#', '.'*depth, branch_name, parent.branch_name)

    return parent.add_child(branch_name, enabled)


def parse(lines: Iterator[str]) -> Stack:
    stack = Stack()
    parents = [stack]
    for i, line in enumerate(lines, start=1):
        logging.debug('reading line [%s]', line)
        try:
            child = parse_line(line, parents)
            parents.append(child)
        except GhitError as e:
            raise GhitError(f'line {i}: {e}') from e
    return stack


def open_stack(filename: Path | None) -> Stack | None:
    if filename is None or not filename.is_file():
        return None
    with filename.open() as f:
        return parse(f.readlines())
