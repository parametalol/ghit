`ghit` Command Line Utility
===========================

:warning: Work in progress.

Features
--------

* Stack display with `ghit ls` or `ghit -v ls` shows:
  * the branch tree
  * the relation to the base branch state
  * the PR state, if any
  * the unresolved PR comments, if any
* Stack navigation (checkout):
  * `ghit up`, `ghit down`, `ghit top`, `ghit bottom`
* Stack initialization with `ghit init`:
  * creates `.ghit.stack` with the current branch as the main branch
  * adds `.ghit.stack` to `.gitignore`
* Stack manipulation: `ghit branch create <name>`:
  * create and switch to the new branch
  * add new branch name to `.ghit.stack`
* Stack or branch publication with `ghit stack submit` or `ghit branch submit`:
  * pushes branch(es) upstream with no force, so may fail after rebase
  * creates or updates GitHub PR(s)
  * creates or updates dependencies comment(s)
* Check that branches in a stack sit on the heads of their parents with `ghit stack check`

Installation
------------

```sh
python3 -m pip install ghit-smartptr
```
