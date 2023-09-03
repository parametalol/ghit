import unittest
from dataclasses import dataclass

from ghit.graphql import (
    Pages,
    cursor_or_null,
    edges,
    end_cursor,
    fields,
    func,
    input,
    last_edge_cursor,
    obj,
    on,
    paged,
    path,
)


@dataclass
class TestSubClass:
    value: str


@dataclass
class TestClass:
    value: str
    subclasses: Pages[TestSubClass]


class TestGraphQL(unittest.TestCase):
    def test_fields(self):
        self.assertEqual("a b c", fields("a", "b", "c"))
        self.assertEqual("", fields())

    def test_on(self):
        self.assertEqual("... on x{  }", on("x"))
        self.assertEqual("... on x{ y }", on("x", "y"))

    def test_obj(self):
        self.assertEqual("x{ y }", obj("x", "y"))
        self.assertEqual("x{ a b }", obj("x", "a", "b"))
        self.assertEqual("x{ a b }", obj("x", fields("a", "b")))

    def test_func(self):
        self.assertEqual(
            'f(a: 1, b: "word"){ c d }',
            func("f", {"a": 1, "b": '"word"'}, "c", "d"),
        )

        self.assertEqual(
            'f(a: 1, b: "word"){ c{ d } e{ f } }',
            func("f", {"a": 1, "b": '"word"'}, obj("c", "d"), obj("e", "f")),
        )
        f = func(
            "func",
            {"a": 1, "b": '"word"'},
            obj("pageInfo", "endCursor", "hasNextPage"),
            obj("edges", "cursor", obj("node", *["1", "2"])),
        )

        self.assertEqual(
            'func(a: 1, b: "word"){ pageInfo{ endCursor hasNextPage } '
            + "edges{ cursor node{ 1 2 } } }",
            f,
        )

    def test_paged(self):
        self.assertEqual(
            'object(a: 1, b: "word"){ pageInfo{ endCursor hasNextPage } '
            + "edges{ cursor node{ c d } } }",
            paged("object", {"a": 1, "b": '"word"'}, "c", "d"),
        )

    def test_cursor_or_null(self):
        self.assertEqual('"x"', cursor_or_null("x"))
        self.assertEqual("null", cursor_or_null(None))

    def test_input(self):
        self.assertDictEqual({"input": "{ a: a, b: b }"}, input(a="a", b="b"))

    def test_Pages(self):
        response = {
            "data": {
                "search": {
                    "pageInfo": {"endCursor": "A", "hasNextPage": False},
                    "edges": [
                        {
                            "cursor": "A",
                            "node": {
                                "value": "test one",
                                "subClasses": {
                                    "pageInfo": {
                                        "endCursor": "B",
                                        "hasNextPage": True,
                                    },
                                    "edges": [
                                        {
                                            "cursor": "B",
                                            "node": {"value": "subtest one"},
                                        }
                                    ],
                                },
                            },
                        }
                    ],
                }
            }
        }

        def make_tsc(edge) -> TestSubClass:
            node = edge["node"]
            return TestSubClass(node["value"])

        def make_tc(edge) -> TestClass:
            node = edge["node"]
            return TestClass(
                node["value"],
                subclasses=Pages("subClasses", make_tsc, node),
            )

        tcs = Pages("search", make_tc)
        tcs.append_all(lambda c: response["data"])
        self.assertEqual(1, len(tcs.data))
        self.assertEqual("test one", tcs.data[0].value)
        self.assertEqual(1, len(tcs.data[0].subclasses.data))
        self.assertEqual("subtest one", tcs.data[0].subclasses.data[0].value)

        self.assertFalse(tcs.data[0].subclasses.complete())

        tcs.data[0].subclasses.append_all(
            lambda c: {
                "data": {
                    "testClass": {
                        "value": "test one",
                        "subClasses": {
                            "pageInfo": {
                                "endCursor": "C",
                                "hasNextPage": False,
                            },
                            "edges": [
                                {
                                    "cursor": "C",
                                    "node": {"value": "subtest two"},
                                }
                            ],
                        },
                    },
                }
            }["data"]["testClass"]
        )
        self.assertEqual(2, len(tcs.data[0].subclasses.data))
        self.assertEqual("subtest two", tcs.data[0].subclasses.data[1].value)

    def test_path(self):
        self.assertEqual("abc", path({"a": "abc"}, "a"))
        self.assertEqual("abc", path(["abc"], 0))
        self.assertEqual(
            "abc", path({"a": {"b": ["x", "y", "abc"]}}, "a", "b", -1)
        )

    def test_edges(self):
        data = {
            "subClasses": {
                "pageInfo": {
                    "endCursor": "C",
                    "hasNextPage": False,
                },
                "edges": [
                    {
                        "cursor": "C",
                        "node": {"value": "subtest two"},
                    }
                ],
            },
        }

        e = next(edges(data, "subClasses"))
        self.assertEqual("C", e["cursor"])

    def test_cursor(self):
        data = {
            "subClasses": {
                "pageInfo": {
                    "endCursor": "C",
                    "hasNextPage": False,
                },
                "edges": [
                    {
                        "cursor": "A",
                        "node": {"value": "subtest two"},
                    },
                    {
                        "cursor": "B",
                        "node": {"value": "subtest two"},
                    },
                ],
            },
        }
        self.assertEqual("B", last_edge_cursor(data, "subClasses"))
        c, has_next = end_cursor(data, "subClasses")
        self.assertEqual("C", c)
        self.assertFalse(has_next)
        data["subClasses"]["pageInfo"]["hasNextPage"] = True
        c, has_next = end_cursor(data, "subClasses")
        self.assertTrue(has_next)
