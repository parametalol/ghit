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
* Stack navigation: `ghit up`, `ghit down`, `ghit top`, `ghit bottom`
* Stack initialization with `ghit init`
  * create `.ghit.stack` with the current branch as the main branch
  * add `.ghit.stack` to `.gitignore`
* Stack manipulation: `ghit branch create <name>`
  * create and switch to the new branch
  * add new branch name to `.ghit.stack`
* Stack publication with `ghit stack update`:
  * push branches upstream
  * create or update GitHub PRs
  * create or update dependencies comment

Installation
------------

```sh
python3 -m pip install ghit-smartptr
```
