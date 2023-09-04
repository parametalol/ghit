`ghit` Command Line Utility
===========================

:warning: Work in progress.

Features
--------

* Stack display with `ghit ls` or `ghit -v ls`
  * branch tree
  * base state
  * PR state
  * unresolved PR comments
* Stack navigation (checkout): `ghit up`, `ghit down`, `ghit top`, `ghit bottom`
* Stack initialization with `ghit init`
  * create `.ghit.stack` with the current branch as the main branch
  * add `.ghit.stack` to `.gitignore`
* Stack manipulation: `ghit branch create <name>`
  * create and switch to the new branch
  * add new branch name to `.ghit.stack`
* Stack or branch publication with `ghit stack submit` or `ghit branch submit`:
  * push branch(es) upstream
  * create or update GitHub PR(s)
  * create or update dependencies comment(s)
* Check that branches in a stack sit on the heads of their parents with `ghit stack check`

Installation
------------

```sh
python3 -m pip install ghit-smartptr
```
