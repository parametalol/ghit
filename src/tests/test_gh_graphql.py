import unittest

from ghit.gh_graphql import first_n_after, pr_details_query


class TestGraphQL(unittest.TestCase):
    def test_first_n_after(self):
        assert first_n_after('test', 'obj', 10, 'after', opt='opt') == (
            'test(first: 10, after: "after", opt: opt)'
            '{ pageInfo{ endCursor hasNextPage } '
            'edges{ cursor node{ obj } } }'
        )

    def test_pr_details(self):
        q = pr_details_query('pr_test', lambda after: first_n_after('test', 'obj', 10, after))
        assert q('owner', 'repository', 42, 'abc') == (
            'query pr_test{ repository(owner: "owner", name: "repository")'
            '{ pullRequest(number: 42)'
            '{ test(first: 10, after: "abc")'
            '{ pageInfo{ endCursor hasNextPage } '
            'edges{ cursor node{ obj } } } } } }'
        )
