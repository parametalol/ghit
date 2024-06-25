from ghit.gh import COMMENT_BEGIN, COMMENT_END, COMMENT_FIRST_LINE, _find_stack_comment, _patch_body


def test_find_stack_comment():
    assert _find_stack_comment('body') is None
    body = ['body', COMMENT_BEGIN, COMMENT_FIRST_LINE, COMMENT_END]
    assert _find_stack_comment('\n'.join(body)) == (5,105)

def test_patch_body():
    assert _patch_body('body', 'comment') == 'body\ncomment'
    body = ['body', COMMENT_BEGIN, COMMENT_FIRST_LINE, COMMENT_END]
    assert _patch_body('\n'.join(body), 'comment') == 'body\ncomment'
