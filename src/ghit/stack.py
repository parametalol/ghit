import os
from collections.abc import Iterator


class StackRecord:
    def __init__(
        self,
        parent: any,
        branch_name: str | None,
        depth: int,
        children: int,
        index: int,
    ):
        self.parent: StackRecord | None = parent
        self.branch_name = branch_name
        self.depth = depth
        self.children = children
        self.index = index


class Stack:
    def __init__(self) -> None:
        self._stack: dict[str, Stack] = {}

    def add_child(self, parents: list[str], child: str):
        if child.startswith("#"):
            return
        branch = child.lstrip(".")
        depth = len(child) - len(branch)
        for _ in range(0, len(parents) - depth):
            parents.pop()
        parents.append(branch)
        s = self
        for p in range(0, depth):
            s = s._stack[parents[p]]
        s._stack[branch] = Stack()

    def is_empty(self) -> bool:
        return len(self._stack) == 0

    def _traverse(
        self, parent: StackRecord = None, depth: int = 0
    ) -> Iterator[StackRecord]:
        i = 0
        for branch_name, substack in self._stack.items():
            current = StackRecord(parent, branch_name, depth, len(substack._stack), i)
            yield current
            i += 1
            if not substack.is_empty():
                yield from substack._traverse(current, depth + 1)

    def traverse(self) -> Iterator[StackRecord]:
        yield from self._traverse()

    def _find_depth(self)->int:
        depth = 0
        for record in self.traverse():
            depth = max(depth, record.depth)
        return depth
    
    def rtraverse(self) -> Iterator[StackRecord]:
        depth = self._find_depth()
        while depth:
            for record in self.traverse():
                if record.depth == depth:
                    yield record
            depth -= 1


def open_stack(filename: str) -> Stack | None:
    if not os.path.isfile(filename):
        return None
    stack = Stack()
    parents = list[str]()
    with open(filename) as f:
        for line in f.readlines():
            stack.add_child(parents, line.rstrip())
    return stack
