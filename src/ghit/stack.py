from __future__ import annotations
import os
from collections.abc import Iterator
import logging


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
        if self.is_root():
            return None
        p = self.__parent
        return p if p._enabled else p.get_parent()

    def add_child(self, branch_name: str, enabled: bool = True) -> Stack:
        if branch_name in self._children:
            raise Exception(
                f"'{branch_name}' already exist in '{self.branch_name}'"
            )
        child = Stack(branch_name, enabled, self)
        self._children.update({branch_name: child})
        return child

    def is_last_child(self) -> bool:
        return self.is_root() or self._index == self.get_parent().length() - 1

    def length(self) -> int:
        return len(self._children)

    def is_root(self) -> bool:
        return self.__parent is None

    def traverse(self, with_first_level: bool = True) -> Iterator[Stack]:
        if (
            not self.is_root()
            and self._enabled
            and (self.get_parent() or with_first_level)
        ):
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

    def dumps(self, lines: list[str] = []):
        if not self.is_root():
            lines.append(
                ("" if self._enabled else "#")
                + "." * (self.depth - 1)
                + self.branch_name
            )
        for record in self._children.values():
            record.dumps(lines)


def open_stack(filename: str) -> Stack | None:
    if not os.path.isfile(filename):
        return None
    stack = Stack()
    parents = [stack]
    with open(filename) as f:
        for line in f.readlines():
            line = line.rstrip()
            logging.debug(f"reading line {line}")
            logging.debug(f"parents: {[p.branch_name for p in parents]}")

            enabled = not line.startswith("#")
            line = line.lstrip("#")
            branch_name = line.lstrip(".")
            if not branch_name:
                continue
            depth = len(line) - len(branch_name)
            logging.debug(
                f"parsed: {enabled} {branch_name} {depth}."
            )
            logging.debug(f"current parent: {parents[-1].branch_name}.")

            for _ in range(1, len(parents) - depth):
                parents.pop()
            child = parents[-1].add_child(branch_name, enabled)
            parents.append(child)
    return stack
