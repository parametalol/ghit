import logging
from typing import TypeVar, Generic, Callable
from collections.abc import Iterator

# region builder


def fields(*f: str) -> str:
    return " ".join(f)


def obj(name: str, *f: str) -> str:
    return name + "{ " + fields(*f) + " }"


def on(t: str, *f) -> str:
    return obj(f"... on {t}", *f)


query = obj


def func(name: str, args: dict[str, str], *f: str) -> str:
    extra = ", ".join(f"{k}: {v}" for k, v in args.items())
    return obj(f"{name}({extra})", *f)


def paged(name: str, args: dict[str, str], *f: str) -> str:
    return func(
        name,
        args,
        obj("pageInfo", "endCursor", "hasNextPage"),
        obj("edges", "cursor", obj("node", *f)),
    )


# endregion builder

T = TypeVar("T")


class Pages(Generic[T]):
    def __init__(
        self,
        name: str,
        obj_ctor: Callable[[any], T],
        node: any = None,
    ) -> None:
        super().__init__()
        self.name = name
        self.obj_ctor = obj_ctor
        self.next_cursor: str = last_edge_cursor(node, name)
        self.end_cursor, self.has_next_page = (
            end_cursor(node, name) if node else (None, True)
        )
        self.data = list(map(obj_ctor, edges(node, name))) if node else []

    def complete(self) -> bool:
        return self.next_cursor == self.end_cursor and not self.has_next_page

    def append_all(self, next_page) -> None:
        while not self.complete():
            logging.debug(
                f"querying {self.name} after cursor {self.next_cursor}"
            )
            data = next_page(self.next_cursor)
            logging.debug(f"data={data}")
            if not data:
                raise Exception("No data in response")
            self.end_cursor, self.has_next_page = end_cursor(data, self.name)
            new_data = list(map(self.obj_ctor, edges(data, self.name)))
            self.data.extend(new_data)
            self.next_cursor = last_edge_cursor(data, self.name)
            if not self.has_next_page:
                logging.debug(f"queried all {self.name}")


# region helpers


def cursor_or_null(c: str | None) -> str:
    return f'"{c}"' if c else "null"


def input(**args) -> dict[str, str]:
    extra = ", ".join(f"{k}: {v}" for k, v in args.items())
    return {"input": f"{{ {extra} }}"}


def path(obj: any, *keys: str | int) -> any:
    if not obj:
        return None
    for k in keys:
        if isinstance(obj, list):
            if obj and len(obj) > (k if k >= 0 else len(obj) + k):
                obj = obj[k]
                continue
        elif k in obj:
            obj = obj[k]
            continue
        return None
    return obj


def edges(obj: any, name: str) -> Iterator[any]:
    edges = path(obj, name, "edges")
    if edges:
        for edge in edges:
            yield edge


def last_edge_cursor(obj: any, field: str) -> str:
    return path(obj, field, "edges", -1, "cursor")


def end_cursor(obj: any, field: str) -> tuple[str, bool]:
    if not obj:
        return None, False
    return path(obj, field, "pageInfo", "endCursor"), bool(
        path(obj, field, "pageInfo", "hasNextPage")
    )


# endregion helpers
