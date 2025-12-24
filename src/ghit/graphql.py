from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


# GraphQL scalar types
type GqlScalar = str | int | float | bool | None

# Any value that can appear in a GraphQL response (recursive)
type GqlValue = GqlScalar | list[GqlValue] | dict[str, GqlValue]

# A GraphQL JSON node: a dict with string keys and GqlValue values
type GqlNode = dict[str, GqlValue]

# region builder


def fields(*f: str) -> str:
    return ' '.join(f)


def obj(name: str, *f: str) -> str:
    return name + '{ ' + fields(*f) + ' }'


def on(t: str, *f) -> str:
    return obj(f'... on {t}', *f)


query = obj


def func(name: str, args: dict, *f: str) -> str:
    extra = ', '.join(f'{k}: {v}' for k, v in args.items())
    return obj(f'{name}({extra})', *f)


def paged(name: str, args: dict, *f: str) -> str:
    return func(
        name,
        args,
        obj('pageInfo', 'endCursor', 'hasNextPage'),
        obj('edges', 'cursor', obj('node', *f)),
    )


# endregion builder


class Pages[T]:
    def __init__(
        self,
        name: str,
        obj_ctor: Callable[[GqlNode], T],
        node: GqlNode | None = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.obj_ctor = obj_ctor
        self.next_cursor: str | None = last_edge_cursor(node, name)
        self.end_cursor, self.has_next_page = end_cursor(node, name) if node else (None, True)
        self.data = list(map(obj_ctor, edges(node, name))) if node else []

    def complete(self) -> bool:
        return self.next_cursor == self.end_cursor and not self.has_next_page

    def append_all(self, next_page) -> None:
        while not self.complete():
            logging.debug('querying %s after cursor %s', self.name, self.next_cursor)
            data = next_page(self.next_cursor)
            logging.debug('data=%s', data)
            if not data:
                raise Exception('No data in response')
            self.end_cursor, self.has_next_page = end_cursor(data, self.name)
            new_data = list(map(self.obj_ctor, edges(data, self.name)))
            self.data.extend(new_data)
            self.next_cursor = last_edge_cursor(data, self.name)
            if not self.has_next_page:
                logging.debug('queried all %s', self.name)


# region helpers


def cursor_or_null(c: str | None) -> str:
    return f'"{c}"' if c else 'null'


def input(**args) -> dict[str, str]:
    extra = ', '.join(f'{k}: {v}' for k, v in args.items())
    return {'input': f'{{ {extra} }}'}


def path(node: GqlNode | None, *keys: str | int) -> GqlValue:
    if not node:
        return None
    current: GqlValue = node
    for k in keys:
        if isinstance(current, list) and isinstance(k, int):
            if current and len(current) > (k if k >= 0 else len(current) + k):
                current = current[k]
                continue
        elif isinstance(current, dict) and k in current:
            current = current[k]
            continue
        return None
    return current


def edges(node: GqlNode | None, name: str) -> Iterator[GqlNode]:
    edge_list = path(node, name, 'edges')
    if edge_list and isinstance(edge_list, (list, dict)):
        yield from edge_list


def last_edge_cursor(node: GqlNode | None, field: str) -> str | None:
    result = path(node, field, 'edges', -1, 'cursor')
    return str(result) if result is not None else None


def end_cursor(node: GqlNode | None, field: str) -> tuple[str | None, bool]:
    if not node:
        return None, False
    result = path(node, field, 'pageInfo', 'endCursor')
    return (str(result) if result is not None else None), bool(path(node, field, 'pageInfo', 'hasNextPage'))


# endregion helpers
