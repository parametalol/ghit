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

Example Flow
------------
```console
localhost:my-git-repo (main)$ ghit init
localhost:my-git-repo (main)$ cat .ghit.stack 
main
localhost:my-git-repo (main)$ git add .gitignore
localhost:my-git-repo (main)$ git commit -m "add .ghit.stack to .gitignore"
```
```console
localhost:my-git-repo (main)$ ghit branch create new-feature
Checked-out new-feature.
The branch doesn't have an upstream.
localhost:my-git-repo (new-feature)$ cat .ghit.stack 
main
.new-feature
```
```console
localhost:my-git-repo (new-feature)$ git add .
localhost:my-git-repo (new-feature)$ git commit
localhost:my-git-repo (new-feature)$ ghit ls
  main
⯈ └─ new-feature *
localhost:my-git-repo (new-feature)$ ghit stack submit
Pushed new-feature to remote git@github.com:me/my-git-repo.git.
Set upstream to origin/new-feature.
Created PR #73 (OPEN).
localhost:my-git-repo (new-feature)$ ghit ls
  main
⯈ └─ new-feature #73 (OPEN)✓ new-feature
```
```console
localhost:my-git-repo (new-feature)$ ghit top
Checked-out main.
localhost:my-git-repo (main)$ ghit ls
⯈ main
  └─ new-feature #73 (OPEN)✓ new-feature
```
