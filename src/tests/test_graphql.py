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
        assert fields('a', 'b', 'c') == 'a b c'
        assert fields() == ''

    def test_on(self):
        assert on('x') == '... on x{  }'
        assert on('x', 'y') == '... on x{ y }'

    def test_obj(self):
        assert obj('x', 'y') == 'x{ y }'
        assert obj('x', 'a', 'b') == 'x{ a b }'
        assert obj('x', fields('a', 'b')) == 'x{ a b }'

    def test_func(self):
        assert func('f', {'a': 1, 'b': '"word"'}, 'c', 'd') == 'f(a: 1, b: "word"){ c d }'

        assert func('f', {'a': 1, 'b': '"word"'}, obj('c', 'd'), obj('e', 'f')) == 'f(a: 1, b: "word"){ c{ d } e{ f } }'
        f = func(
            'func',
            {'a': 1, 'b': '"word"'},
            obj('pageInfo', 'endCursor', 'hasNextPage'),
            obj('edges', 'cursor', obj('node', *['1', '2'])),
        )

        assert 'func(a: 1, b: "word"){ pageInfo{ endCursor hasNextPage } ' + 'edges{ cursor node{ 1 2 } } }' == f

    def test_paged(self):
        assert 'object(a: 1, b: "word"){ pageInfo{ endCursor hasNextPage } ' + 'edges{ cursor node{ c d } } }' == paged(
            'object', {'a': 1, 'b': '"word"'}, 'c', 'd'
        )

    def test_cursor_or_null(self):
        assert cursor_or_null('x') == '"x"'
        assert cursor_or_null(None) == 'null'

    def test_input(self):
        assert input(a='a', b='b') == {'input': '{ a: a, b: b }'}

    def test_pages_class(self):
        response = {
            'data': {
                'search': {
                    'pageInfo': {'endCursor': 'A', 'hasNextPage': False},
                    'edges': [
                        {
                            'cursor': 'A',
                            'node': {
                                'value': 'test one',
                                'subClasses': {
                                    'pageInfo': {
                                        'endCursor': 'B',
                                        'hasNextPage': True,
                                    },
                                    'edges': [
                                        {
                                            'cursor': 'B',
                                            'node': {'value': 'subtest one'},
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
            node = edge['node']
            return TestSubClass(node['value'])

        def make_tc(edge) -> TestClass:
            node = edge['node']
            return TestClass(
                node['value'],
                subclasses=Pages('subClasses', make_tsc, node),
            )

        tcs = Pages('search', make_tc)
        tcs.append_all(lambda c: response['data'])
        assert len(tcs.data) == 1
        assert tcs.data[0].value == 'test one'
        assert len(tcs.data[0].subclasses.data) == 1
        assert tcs.data[0].subclasses.data[0].value == 'subtest one'

        assert not tcs.data[0].subclasses.complete()

        tcs.data[0].subclasses.append_all(
            lambda c: {
                'data': {
                    'testClass': {
                        'value': 'test one',
                        'subClasses': {
                            'pageInfo': {
                                'endCursor': 'C',
                                'hasNextPage': False,
                            },
                            'edges': [
                                {
                                    'cursor': 'C',
                                    'node': {'value': 'subtest two'},
                                }
                            ],
                        },
                    },
                }
            }['data']['testClass']
        )
        assert len(tcs.data[0].subclasses.data) == 2  # noqa: PLR2004
        assert tcs.data[0].subclasses.data[1].value == 'subtest two'

    def test_path(self):
        assert path({'a': 'abc'}, 'a') == 'abc'
        assert path(['abc'], 0) == 'abc'
        assert path({'a': {'b': ['x', 'y', 'abc']}}, 'a', 'b', -1) == 'abc'

    def test_edges(self):
        data = {
            'subClasses': {
                'pageInfo': {
                    'endCursor': 'C',
                    'hasNextPage': False,
                },
                'edges': [
                    {
                        'cursor': 'C',
                        'node': {'value': 'subtest two'},
                    }
                ],
            },
        }

        e = next(edges(data, 'subClasses'))
        assert e['cursor'] == 'C'

    def test_cursor(self):
        data = {
            'subClasses': {
                'pageInfo': {
                    'endCursor': 'C',
                    'hasNextPage': False,
                },
                'edges': [
                    {
                        'cursor': 'A',
                        'node': {'value': 'subtest two'},
                    },
                    {
                        'cursor': 'B',
                        'node': {'value': 'subtest two'},
                    },
                ],
            },
        }
        assert last_edge_cursor(data, 'subClasses') == 'B'
        c, has_next = end_cursor(data, 'subClasses')
        assert c == 'C'
        assert not has_next
        data['subClasses']['pageInfo']['hasNextPage'] = True
        c, has_next = end_cursor(data, 'subClasses')
        assert has_next
