import pytest
from ghit.error import GhitError
from ghit.stack import Stack, parse, parse_line


def test_get_parent():
    stack = Stack()
    parents = [stack]
    assert stack.get_parent() is None
    child = parse_line('main', parents)
    assert child.get_parent() is None


def test_parse_line():
    stack = Stack()
    parents = [stack]
    child = parse_line('main', parents)
    assert child.get_parent() is None
    assert stack._children['main'].branch_name == 'main'
    assert child.branch_name == 'main'
    assert child.depth == 0

    child = parse_line('.a1', parents)
    assert child.branch_name == 'a1'
    assert child.depth == 1
    assert child.get_parent().branch_name == 'main'

    child = parse_line('..a2', parents)
    assert child.branch_name == 'a2'
    assert child.depth == 2  # noqa: PLR2004
    assert child.get_parent().branch_name == 'a1'

    child = parse_line('..a21', parents)
    assert child.branch_name == 'a21'
    assert child.depth == 2  # noqa: PLR2004
    assert child.get_parent().branch_name == 'a1'

    child = parse_line('.b1', parents)
    assert child.branch_name == 'b1'
    assert child.depth == 1
    assert child.get_parent().branch_name == 'main'

    child = parse_line('dev', parents)
    assert child.branch_name == 'dev'
    assert child.depth == 0
    assert child.get_parent() is None


def test_disabled():
    stack = Stack()
    parents = [stack]
    child = parse_line('main', parents)

    child = parse_line('#.a1', parents)
    assert child.branch_name == 'a1'
    assert child.depth == 1

    child = parse_line('..a2', parents)
    assert child.branch_name == 'a2'
    assert child.depth == 2  # noqa: PLR2004
    assert child.get_parent().branch_name == 'main'

    child = parse_line('..a21', parents)
    assert child.branch_name == 'a21'
    assert child.depth == 2  # noqa: PLR2004
    assert child.get_parent().branch_name == 'main'

    child = parse_line('.b1', parents)
    assert child.branch_name == 'b1'
    assert child.depth == 1
    assert child.get_parent().branch_name == 'main'

    child = parse_line('dev', parents)
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

    s = stack.find('main')
    assert s.get_parent() is None
    assert s.get_parent(True).branch_name is None

    s = stack.find('a2')
    assert s.get_parent().branch_name == 'main'
    assert s.get_parent(True).branch_name == 'disabled'

    s = stack.find('a21')
    assert s.get_parent().branch_name == 'main'
    assert s.get_parent(True).branch_name == 'disabled'

    s = stack.find('a3')
    assert s.get_parent().branch_name == 'a21'
    assert s.get_parent(True).branch_name == 'a21'

    s = stack.find('a22')
    assert s.get_parent().branch_name == 'main'
    assert s.get_parent(True).branch_name == 'disabled'

    s = stack.find('b1')
    assert s.get_parent().branch_name == 'main'
    assert s.get_parent(True).branch_name == 'main'

    s = stack.find('b2')
    assert s.get_parent().branch_name == 'b1'
    assert s.get_parent(True).branch_name == 'b1'

    s = stack.find('disabled')
    assert s.get_parent().branch_name == 'main'
    assert s.get_parent(True).branch_name == 'main'
