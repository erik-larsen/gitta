# Gitta
_There are many like this, but this one is mine._

A tool to manage multiple repos.

## Quick start

#### `gitta.py -u` or `gitta.py`
Probably the most frequently used option, this looks at all your local repos and does a fetch and pull (if no active local changes) on each to get them up to date with remote.  Helpful if you are doing work on one repo across multiple machines.

#### `gitta.py -ca erik-larsen`
Clone all repos under a username.  For any repos you already have cloned, works the same as -u (fetch & pull).  Helpful if you have a new machine and want to get all your repos.  

#### `gitta.py -l erik-larsen`
See what repos are available from a username.

## Usage

```
gitta.py -h             
usage: gitta.py [-h] [-l] [-ca] [-u] [username]

Github repo management tool

positional arguments:
  username          GitHub username to target (required for --list and --clone-all)

options:
  -h, --help        show this help message and exit
  -u, --update      Update all local repos in the current directory
  -ca, --clone-all  Clone/update all public repos for username
  -l, --list        List all public repos for username
```
