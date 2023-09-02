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
* Stack manipulation: `ghit branch create <name>`
* Stack publication with `ghit stack update`:
  * push branches upstream
  * create or update GitHub PRs
  * create or update dependencies comment

Installation
------------

```sh
python3 -m pip install ghit-smartptr
```
