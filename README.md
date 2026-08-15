# Gitta
_There are many like this, but this one is mine._

A tool to manage multiple repos.

Run it from a directory containing your git repos (e.g. `~/Github`) — all commands operate on the repos found there.

## Quick start

#### `gitta.py -s` or just `gitta.py`
The default. Show a compact table of all your local repos: user.name/user.email, branch, commits to pull/push, and files to commit/add.  Read-only and fast — no fetching, pulling, or prompting.

```
REPO                       USER                                  BRANCH      TO PULL      TO PUSH      TO COMMIT  TO ADD
emscripten-sdl2-ogles2     erik-larsen, erik.3d.pixel@gmail.com  master      -            -            -          -
hello-vt                   erik-larsen, erik.3d.pixel@gmail.com  main        5 commits    -            6 files    1 files
opengl-for-mac             erik-larsen, erik.3d.pixel@gmail.com  main        -            -            -          -
```

Note: since -s never touches the network, TO PULL reflects the remote as of each repo's last fetch.  Run -u to actually check the remote.

#### `gitta.py -u` or `gitta.py -u myrepo`
Get up to date with the remote on all your local repos (or just one, if named).  Helpful if you are doing work on the same repos across multiple machines.  For each repo:

1. Checks that a local user.name and user.email are set, and prompts if not — offering the repo owner (from the remote URL) as the default, plus a most-recently-used list of identities seen so far in the run.
2. Warns if the local user.name doesn't match the repo owner.
3. Sets credential.username to the repo owner (HTTPS remotes, owned repos only, never overwrites an existing value), so pushes authenticate as the right GitHub account.  This needs a credential helper that keeps per-account tokens — e.g. `gh auth login` for each account, then `gh auth setup-git`.
4. Fetches, then fast-forwards — but only if the repo is actually behind its upstream.  Repos with local changes or a diverged branch are left untouched and flagged.

Ends with a summary of which repos are clean, which have work in progress, and which are owned by someone else.

#### `gitta.py -l erik-larsen`
See what public repos are available from a username, with license, stars, and forks.

```
REPO                           LICENSE     STARS  FORKS
ammo.js                        Other           8      4
api-reference                  MIT             7      3
awesome-playcanvas             CC0-1.0       474     61
basis_universal                Apache-2.0      2      4
```

#### `gitta.py -ca erik-larsen`
Clone all public repos under a username.  Repos you already have are updated (fetch & fast-forward) instead.  Helpful if you have a new machine and want to get all your repos.

## Usage

```
gitta.py -h
usage: gitta.py [-h] [-l] [-ca] [-u [REPO]] [-s] [username]

Github repo management tool

positional arguments:
  username              GitHub username to target (required for --list and
                        --clone-all)

options:
  -h, --help            show this help message and exit
  -l, --list            List all public repos for username
  -ca, --clone-all      Clone/update all public repos for username
  -u [REPO], --update [REPO]
                        Update (fetch & fast-forward) all local repos in the
                        current directory, or just REPO if given
  -s, --status          Show compact git status and user.name/user.email for
                        all local repos in the current directory (default)
```
