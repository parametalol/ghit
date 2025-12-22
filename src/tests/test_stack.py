import pytest

from ghit.error import GhitError
from ghit.stack import Stack, parse, parse_line


def test_get_parent():
    stack = Stack()
    parents = [stack]
    assert stack.get_parent() is None
    child = parse_line('main', parents)
    assert child is not None
    assert child.get_parent() is None


def test_parse_line():
    stack = Stack()
    parents = [stack]
    child = parse_line('main', parents)
    assert child is not None
    assert child.get_parent() is None
    assert stack._children['main'].branch_name == 'main'
    assert child.branch_name == 'main'
    assert child.depth == 0

    child = parse_line('.a1', parents)
    assert child is not None
    assert child.branch_name == 'a1'
    assert child.depth == 1
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'main'

    child = parse_line('..a2', parents)
    assert child is not None
    assert child.branch_name == 'a2'
    assert child.depth == 2  # noqa: PLR2004
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'a1'

    child = parse_line('..a21', parents)
    assert child is not None
    assert child.branch_name == 'a21'
    assert child.depth == 2  # noqa: PLR2004
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'a1'

    child = parse_line('.b1', parents)
    assert child is not None
    assert child.branch_name == 'b1'
    assert child.depth == 1
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'main'

    child = parse_line('dev', parents)
    assert child is not None
    assert child.branch_name == 'dev'
    assert child.depth == 0
    assert child.get_parent() is None

    child = parse_line('', parents)
    assert child is None


def test_disabled():
    stack = Stack()
    parents = [stack]
    child = parse_line('main', parents)

    child = parse_line('#.a1', parents)
    assert child is not None
    assert child.branch_name == 'a1'
    assert child.depth == 1

    child = parse_line('..a2', parents)
    assert child is not None
    assert child.branch_name == 'a2'
    assert child.depth == 2  # noqa: PLR2004
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'main'

    child = parse_line('..a21', parents)
    assert child is not None
    assert child.branch_name == 'a21'
    assert child.depth == 2  # noqa: PLR2004
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'main'

    child = parse_line('.b1', parents)
    assert child is not None
    assert child.branch_name == 'b1'
    assert child.depth == 1
    parent = child.get_parent()
    assert parent is not None
    assert parent.branch_name == 'main'

    child = parse_line('dev', parents)
    assert child is not None
    assert child.branch_name == 'dev'
    assert child.depth == 0
    assert child.get_parent() is None


def test_bad_indent():
    text = ['main', '..a2']
    with pytest.raises(GhitError):
        parse(text)

    text = ['#.disabled', 'main']
    parse(text)


def test_parse():
    text = ['main', '.b1', '..b2']
    stack = parse(text)
    assert stack is not None
    assert stack.dumps() == text


def test_parse_disabled():
    text = ['main', '#.disabled', '..a2', '..a21', '...a3', '..a22', '.b1', '..b2']
    stack = parse(text)
    assert stack is not None
    assert stack.dumps() == text

    cases = [
        # (name, expected_parent_branch_or_None, expected_parent_with_disabled_branch_or_emptystr)
        # use None => parent is None, '' => parent exists but branch_name is None
        ('main', None, ''),          # root has no parent, but get_parent(True) returns root node with branch_name None
        ('a2', 'main', 'disabled'),
        ('a21', 'main', 'disabled'),
        ('a3', 'a21', 'a21'),
        ('a22', 'main', 'disabled'),
        ('b1', 'main', 'main'),
        ('b2', 'b1', 'b1'),
        ('disabled', 'main', 'main'),
    ]

    for name, exp_parent, exp_parent_with_disabled in cases:
        s = stack.find(name)
        assert s is not None

        parent = s.get_parent()
        if exp_parent is None:
            assert parent is None
        else:
            assert parent is not None
            if exp_parent == '':
                assert parent.branch_name is None
            else:
                assert parent.branch_name == exp_parent

        parent_td = s.get_parent(True)
        # exp_parent_with_disabled uses '' to mean parent exists but branch_name is None
        assert (parent_td is not None)
        if exp_parent_with_disabled == '':
            assert parent_td.branch_name is None
        else:
            assert parent_td.branch_name == exp_parent_with_disabled
