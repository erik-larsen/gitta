#!/usr/bin/env python3

import requests
import sys
import os
import subprocess
import argparse

def run_git(command, directory, check=False):
    """
    Runs a git command in a specified directory.
    If check is True, raises CalledProcessError on failure.
    Returns the output.
    """
    try:
        result = subprocess.run(
            ['git'] + command,
            cwd=directory,
            capture_output=True,
            text=True,
            check=check
        )
        return result.stdout.strip()
    except FileNotFoundError:
        print("Error: 'git' command not found. Please ensure Git is installed and in your PATH")
        sys.exit(1)

def get_repo_owner(remote_url):
    """
    Extracts the repository owner from a git remote URL.
    """
    if remote_url.startswith('https://'):
        # HTTPS format: https://github.com/owner/repo.git
        parts = remote_url.split('/')
        if len(parts) >= 4:
            return parts[-2]
    elif remote_url.startswith('git@'):
        # SSH format: git@github.com:owner/repo.git
        parts = remote_url.split(':')
        if len(parts) >= 2:
            owner_and_repo = parts[1].split('/')
            return owner_and_repo[0]
    return None

def _github_headers():
    """
    Returns request headers for the GitHub API. If a GITHUB_TOKEN environment
    variable is set, authenticated requests are used, which raises the rate
    limit from 60 to 5000 requests/hour.
    """
    headers = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers

def print_table(headers, rows, right_align=()):
    """
    Prints rows as a column-aligned table. Column indexes listed in
    right_align are right-justified (for numeric columns).
    """
    widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]
    for row in [headers] + rows:
        cells = [cell.rjust(w) if i in right_align else cell.ljust(w)
                 for i, (cell, w) in enumerate(zip(row, widths))]
        print("  ".join(cells).rstrip())

def list_github_repos(username):
    """
    Fetches all public GitHub repos for a given username.

    Args:
        username (str): The GitHub username.

    Returns:
        list: A list of repo info dicts from the GitHub API, or None if the user is not found.
    """
    url = f"https://api.github.com/users/{username}/repos"

    # Results are paginated, so keep fetching until we get a short page
    repos = []
    page = 1
    per_page = 100
    while True:
        response = requests.get(url, params={'per_page': per_page, 'page': page},
                                headers=_github_headers())

        if response.status_code == 200:
            batch = response.json()
            repos.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        elif response.status_code == 404:
            print(f"User '{username}' not found")
            return None
        else:
            print(f"Error fetching repos. Status code: {response.status_code}")
            return None

    if not repos:
        print(f"User '{username}' has no public repos")
        return []

    return repos

def get_repo_status(repo_path):
    """
    Returns a dict with the repo's branch, upstream behind/ahead counts, and
    pending file counts. behind/ahead are None if no upstream is set.
    Counts are relative to the locally-known remote-tracking ref; a fetch is
    required first for them to reflect the actual remote.
    """
    branch = run_git(['branch', '--show-current'], repo_path) or '(detached)'

    counts = run_git(['rev-list', '--left-right', '--count', '@{upstream}...HEAD'], repo_path)
    if counts:
        behind, ahead = (int(n) for n in counts.split())
    else:
        behind = ahead = None

    to_commit = 0
    to_add = 0
    for line in run_git(['status', '--porcelain'], repo_path).splitlines():
        if line.startswith('??'):
            to_add += 1
        else:
            to_commit += 1

    return {'branch': branch, 'behind': behind, 'ahead': ahead,
            'to_commit': to_commit, 'to_add': to_add}

def show_repo_list(repos):
    """
    Prints a table of repo name, license, stars, and forks from GitHub API repo info.
    """
    if not repos:
        return

    rows = []
    for repo in repos:
        lic = repo.get('license') or {}
        lic_text = lic.get('spdx_id') or ''
        if not lic_text or lic_text == 'NOASSERTION':
            lic_text = lic.get('name') or '-'
        rows.append([repo['name'], lic_text,
                     str(repo['stargazers_count']), str(repo['forks_count'])])

    print_table(["REPO", "LICENSE", "STARS", "FORKS"], rows, right_align={2, 3})

def read_owners_file():
    """Reads a list of usernames from owners.txt in the script's directory."""
    script_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(script_dir, 'owners.txt')

    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except IOError as e:
        print(f"Warning: Could not read {file_path}: {e}")
        return []

def get_github_user_email(username):
    """
    Fetches the public email for a GitHub user. First tries the user profile,
    then falls back to scanning the user's OWN public push events for a commit
    email that verifiably belongs to them (a push can contain commits authored
    by other people, so we must not blindly trust the first email we see).
    """
    headers = _github_headers()
    try:
        # First, try the main user endpoint
        user_url = f"https://api.github.com/users/{username}"
        user_response = requests.get(user_url, headers=headers)
        user_response.raise_for_status()
        user_data = user_response.json()
        if user_data.get('email'):
            return user_data.get('email')

        # Fallback: The 'email' field is often null. Scan the user's public push
        # events, but only accept a commit email we can tie back to this user.
        print(f"User email for '{username}' is private, checking public events for a commit email...")
        login = user_data.get('login') or username
        # Names the commit author must match to be considered "this user".
        identifiers = {s.lower() for s in (login, user_data.get('name')) if s}

        events_url = f"https://api.github.com/users/{username}/events/public"
        events_response = requests.get(events_url, headers=headers)
        events_response.raise_for_status()
        events_data = events_response.json()

        for event in events_data:
            if event.get('type') != 'PushEvent':
                continue
            # Only trust pushes made by the user themselves.
            if (event.get('actor', {}).get('login') or '').lower() != login.lower():
                continue
            for commit in event.get('payload', {}).get('commits', []):
                author = commit.get('author', {})
                author_email = author.get('email')
                if not author_email:
                    continue
                author_name = (author.get('name') or '').lower()
                email_lower = author_email.lower()
                # Accept only if the commit author verifiably is this user:
                # either the author name matches, or it's a GitHub noreply
                # address that encodes the user's login.
                is_owner_noreply = (
                    'users.noreply.github.com' in email_lower
                    and login.lower() in email_lower
                )
                if author_name in identifiers or is_owner_noreply:
                    print(f"Found public commit email for '{username}': {author_email}")
                    return author_email
        return None

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"User '{username}' not found.")
        else:
            print(f"Warning: HTTP error fetching data for '{username}': {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Warning: Network error fetching user data for '{username}': {e}")
        return None

def _update_local_repo(repo_path, repo_name, clean_repos, wip_repos):
    """
    Fetches to refresh remote-tracking refs, then fast-forwards the current
    branch only when it is behind upstream and the working tree is clean.
    Appends the repo name to the appropriate list.
    """
    try:
        # A fetch is unavoidable: without it we can't know whether the remote
        # has new commits. It's a no-op on the wire when nothing changed.
        run_git(['fetch'], repo_path, check=True)
        status = get_repo_status(repo_path)

        if status['to_commit'] or status['to_add']:
            print(f"WARNING: Working tree not clean ({status['to_commit']} to commit, "
                  f"{status['to_add']} to add). Skipping pull")
            wip_repos.append(repo_name)
        elif status['behind'] is None:
            print(f"No upstream set for branch '{status['branch']}'. Nothing to pull")
            clean_repos.append(repo_name)
        elif status['behind'] == 0:
            print("Already up to date")
            clean_repos.append(repo_name)
        elif status['ahead']:
            print(f"WARNING: Branch '{status['branch']}' has diverged from upstream "
                  f"({status['behind']} behind, {status['ahead']} ahead). Skipping merge")
            wip_repos.append(repo_name)
        else:
            print(f"Fast-forwarding {status['behind']} commit(s)..")
            run_git(['merge', '--ff-only', '@{upstream}'], repo_path, check=True)
            clean_repos.append(repo_name)
    except subprocess.CalledProcessError as e:
        print(f"Error updating '{repo_name}': {e}")
        return False
    return True

def clone_or_pull_repos(username, repos):
    """
    Clones or pulls all repos for a given username.

    Args:
        username (str): The GitHub username.
        repos (list): A list of repository names.
    """
    if not repos:
        return

    clean_repos = []
    wip_repos = []

    print(f"Processing repos for '{username}'..")
    for repo_name in repos:
        repo_path = os.path.join(os.getcwd(), repo_name)
        repo_url = f"https://github.com/{username}/{repo_name}.git"

        if os.path.isdir(repo_path):
            print(f"Updating '{repo_name}'..")
            _update_local_repo(repo_path, repo_name, clean_repos, wip_repos)
        else:
            print(f"Cloning '{repo_name}'..")
            try:
                run_git(['clone', repo_url], os.getcwd(), check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error cloning '{repo_name}': {e}")

def find_owner_identity(repo_path, repo_owner):
    """
    Searches the commit history for the most recent commit authored by the
    repo owner and returns its (name, email), or None if no match is found.
    """
    if not repo_owner:
        return None
    log_output = run_git(['log', '--format=%an%x09%ae'], repo_path)
    for line in log_output.splitlines():
        name, _, email = line.partition('\t')
        if repo_owner in name and email:
            return name, email
    return None

def _prompt_for_identity(repo_name, known_identities, repo_owner=None, owner_identity=None):
    """
    Prompts the user to select an existing identity or enter a new one.

    Args:
        repo_name (str): The name of the repository.
        known_identities (list): A list of (username, email) tuples.
        repo_owner (str): The repo owner from the remote URL, offered as option 'O'.
        owner_identity (tuple): The owner's (name, email) found in commit history, if any.

    Returns:
        tuple: A (username, email) tuple for the repository.
    """
    print(f"\nNo complete user identity (name and email) set for '{repo_name}'.")

    # Owner email comes from commit history when found, else from a matching known identity
    if repo_owner and not owner_identity:
        owner_identity = next((ident for ident in known_identities if repo_owner in ident[0]), None)

    # The owner option subsumes its matching identity, so drop the duplicate
    menu_identities = [ident for ident in known_identities if ident != owner_identity]

    if not known_identities and not repo_owner:
        print("No existing identities found. Please enter a new one.")
        new_name = input("Enter user.name: ")
        new_email = input("Enter user.email: ")
        return new_name, new_email

    print("Please choose an identity:")
    if repo_owner:
        if owner_identity:
            print(f"  O: {owner_identity[0]} <{owner_identity[1]}> (repo owner)")
        else:
            print(f"  O: {repo_owner} (repo owner, will prompt for email)")
    for i, (name, email) in enumerate(menu_identities):
        print(f"  {i+1}: {name} <{email}>")

    print("  N: Enter a new identity")

    default_name = repo_owner if repo_owner else menu_identities[0][0]
    prompt = f"Your choice [{default_name}]: "

    while True:
        choice = input(prompt).strip().lower()

        if repo_owner and choice in ('', 'o', '0'):  # Owner is the default
            if owner_identity:
                return owner_identity
            new_email = input(f"Enter user.email for '{repo_owner}': ")
            return repo_owner, new_email

        if not choice and menu_identities:  # Default to the most recent one
            return menu_identities[0]

        if choice == 'n':
            new_name = input("Enter new user.name: ")
            new_email = input("Enter new user.email: ")
            return new_name, new_email

        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(menu_identities):
                return menu_identities[choice_idx]
            else:
                print(f"Invalid number. Please enter a number between 1 and {len(menu_identities)}.")
        except ValueError:
            valid = "a number, 'o', or 'n'" if repo_owner else "a number or 'n'"
            print(f"Invalid input. Please enter {valid}.")

def show_status():
    """
    Shows a table of git status and local user.name/user.email for all repos in the current directory.
    """
    current_dir = os.getcwd()

    def count_text(count, unit):
        return f"{count} {unit}" if count else "-"

    rows = []
    for dir_name in sorted(os.listdir('.')):
        repo_path = os.path.join(current_dir, dir_name)
        if os.path.isdir(repo_path) and '.git' in os.listdir(repo_path):
            local_username = run_git(['config', '--local', 'user.name'], repo_path)
            local_email = run_git(['config', '--local', 'user.email'], repo_path)
            user = f"{local_username or '(not set)'}, {local_email or '(not set)'}"

            status = get_repo_status(repo_path)
            if status['behind'] is not None:
                to_pull = count_text(status['behind'], "commits")
                to_push = count_text(status['ahead'], "commits")
            else:
                to_pull = to_push = "no upstream"

            rows.append([dir_name, user, status['branch'], to_pull, to_push,
                         count_text(status['to_commit'], "files"), count_text(status['to_add'], "files")])

    if not rows:
        print("No git repos found in the current directory")
        return

    print_table(["REPO", "USER", "BRANCH", "TO PULL", "TO PUSH", "TO COMMIT", "TO ADD"], rows)

def update_repos(single_repo=None):
    """
    Updates all local repos in the current directory with the logic from git-update.sh.
    If single_repo is given, only that repo is updated.
    """
    clean_repos = []
    wip_repos = []
    owner_mismatch_repos = []
    known_identities = []

    owners = read_owners_file()
    if owners:
        print(f"Loaded trusted owners from owners.txt: {', '.join(owners)}")

    current_dir = os.getcwd()

    if single_repo:
        repo_path = os.path.join(current_dir, single_repo)
        if not os.path.isdir(repo_path) or '.git' not in os.listdir(repo_path):
            print(f"Error: '{single_repo}' is not a git repo in the current directory")
            sys.exit(1)
        dir_names = [single_repo]
    else:
        dir_names = sorted(os.listdir('.'))

    # Create global gitignore if it doesn't exist
    gitignore_path = os.path.expanduser("~/.gitignore_global")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, 'w') as f:
            f.write(".DS_Store\n")
        run_git(['config', '--global', 'core.excludesfile', gitignore_path], current_dir)
        print("Global .gitignore created and configured successfully")
    else:
        print("Global .gitignore file already exists. Skipping creation")

    for dir_name in dir_names:
        repo_path = os.path.join(current_dir, dir_name)
        if os.path.isdir(repo_path) and dir_name != '.' and '.git' in os.listdir(repo_path):
            print("\n" + "="*64)
            print(f"    CHECKING REPO: {dir_name}")
            print("="*64 + "\n")

            remote_url = run_git(['config', '--get', 'remote.origin.url'], repo_path)
            repo_owner = get_repo_owner(remote_url)

            # Step 1: Check and set local user.name and email
            print("Step 1: check local user.name and email..")
            local_username = run_git(['config', '--local', 'user.name'], repo_path)
            local_email = run_git(['config', '--local', 'user.email'], repo_path)

            if not local_username or not local_email:
                new_username, new_email = (None, None)

                if repo_owner and repo_owner in owners:
                    print(f"Repo owner '{repo_owner}' found in owners.txt. Attempting to set identity.")
                    github_email = get_github_user_email(repo_owner)
                    if github_email:
                        print(f"Found public email for '{repo_owner}': {github_email}")
                        new_username = repo_owner
                        new_email = github_email
                        run_git(['config', '--local', 'user.name', new_username], repo_path)
                        run_git(['config', '--local', 'user.email', new_email], repo_path)
                        local_username = new_username
                        local_email = new_email
                    else:
                        print(f"Could not find a public email for '{repo_owner}'. Please set identity manually.")

                if not local_username or not local_email:
                    owner_identity = find_owner_identity(repo_path, repo_owner)
                    new_username, new_email = _prompt_for_identity(dir_name, known_identities, repo_owner, owner_identity)
                    if new_username and new_email:
                        run_git(['config', '--local', 'user.name', new_username], repo_path)
                        run_git(['config', '--local', 'user.email', new_email], repo_path)
                        local_username = new_username
                        local_email = new_email

            if local_username and local_email:
                identity = (local_username, local_email)
                if identity in known_identities:
                    known_identities.remove(identity)
                known_identities.insert(0, identity)

            print(f"Local user.name:  {local_username}")
            print(f"Local user.email: {local_email}")

            # Step 2: Compare local user to repo owner
            print("\nStep 2: compare local user to repo owner..")
            if not remote_url:
                print("WARNING: No 'origin' remote found. Skipping owner check")
            elif not repo_owner:
                print(f"ERROR: Could not determine repo owner from remote URL: {remote_url}")
            else:
                if repo_owner and local_username and repo_owner in local_username:
                    print(f"OK: Local user.name ('{local_username}') matches repo owner ('{repo_owner}')")
                else:
                    print(f"WARNING: Local user.name ('{local_username}') does NOT match repo owner ('{repo_owner}')")
                    owner_mismatch_repos.append(dir_name)

            print(f"\nStep 3: fetch and fast-forward (if behind and clean) in {dir_name}..")
            _update_local_repo(repo_path, dir_name, clean_repos, wip_repos)

    print("\n" + "="*64)
    print("    REPOS SUMMARY ")
    print("="*64 + "\n")

    print("CLEAN repos (working tree clean and pulled):")
    if not clean_repos:
        print("  None")
    else:
        for repo in clean_repos:
            print(f"    {repo}")

    print("\nWIP repos (working tree not clean or has pending changes):")
    if not wip_repos:
        print("  None")
    else:
        for repo in wip_repos:
            print(f"    {repo}")

    print("\nNON-OWNED repos (user and owner differ):")
    if not owner_mismatch_repos:
        print("  None")
    else:
        for repo in owner_mismatch_repos:
            print(f"    {repo}")

    print("\ndone!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Github repo management tool")
    parser.add_argument("username", nargs='?', default=None, help="GitHub username to target (required for --list and --clone-all)")
    parser.add_argument("-l", "--list", action="store_true", help="List all public repos for username")
    parser.add_argument("-ca", "--clone-all", action="store_true", help="Clone/update all public repos for username")
    parser.add_argument("-u", "--update", nargs='?', const=True, default=False, metavar="REPO",
                        help="Update (fetch & fast-forward) all local repos in the current directory, or just REPO if given")
    parser.add_argument("-s", "--status", action="store_true", help="Show compact git status and user.name/user.email for all local repos in the current directory (default)")

    args = parser.parse_args()

    if args.list or args.clone_all:
        if args.username is None:
            parser.error("The 'username' argument is required for --list or --clone-all options")
        repos = list_github_repos(args.username)
        if repos is not None:
            if args.list:
                show_repo_list(repos)

            if args.clone_all:
                clone_or_pull_repos(args.username, [repo['name'] for repo in repos])

    elif args.status or len(sys.argv) == 1:
        show_status()

    elif args.update:
        update_repos(args.update if isinstance(args.update, str) else None)

    else:
        parser.print_help()
