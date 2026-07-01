# Gitta
_There are many like this, but this one is mine._

A tool to manage multiple repos.

## Quick start

#### `gitta.py -s`
Show a compact table of all your local repos: user.name/user.email, branch, commits to pull/push, and files to commit/add.  Read-only — no fetching, pulling, or prompting.

```
REPO                       USER                                  BRANCH      TO PULL      TO PUSH      TO COMMIT  TO ADD
emscripten-sdl2-ogles2     erik-larsen, erik.3d.pixel@gmail.com  master      -            -            -          -
hello-vt                   erik-larsen, erik.3d.pixel@gmail.com  main        5 commits    -            6 files    1 files
opengl-for-mac             erik-larsen, erik.3d.pixel@gmail.com  main        -            -            -          -
```

#### `gitta.py -u` or `gitta.py`
Get up to date with remote on all your local repos by doing a fetch and pull (if no active local changes) on each of them. Helpful if you are doing work on the same repos across multiple machines.

#### `gitta.py -l erik-larsen`
See what repos are available from a username.

#### `gitta.py -ca erik-larsen`
Clone all repos under a username.  For any repos you already have cloned, works the same as -u (fetch & pull).  Helpful if you have a new machine and want to get all your repos.

## Usage

```
gitta.py -h
usage: gitta.py [-h] [-l] [-ca] [-u] [-s] [username]

Github repo management tool

positional arguments:
  username          GitHub username to target (required for --list and --clone-all)

options:
  -h, --help        show this help message and exit
  -l, --list        List all public repos for username
  -ca, --clone-all  Clone/update all public repos for username
  -u, --update      Update (fetch & pull) all local repos in the current directory
  -s, --status      Show compact git status and user.name/user.email for all local repos in the current directory
```
