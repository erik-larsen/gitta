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

def list_github_repos(username):
    """
    Lists all public GitHub repos for a given username.

    Args:
        username (str): The GitHub username.

    Returns:
        list: A list of repository names, or None if the user is not found.
    """
    url = f"https://api.github.com/users/{username}/repos"
    response = requests.get(url)

    if response.status_code == 200:
        repos = response.json()
        if not repos:
            print(f"User '{username}' has no public repos")
            return []

        repo_names = [repo['name'] for repo in repos]
        return repo_names
    elif response.status_code == 404:
        print(f"User '{username}' not found")
        return None
    else:
        print(f"Error fetching repos. Status code: {response.status_code}")
        return None

def _update_local_repo(repo_path, repo_name, clean_repos, wip_repos):
    """
    Performs a fetch, status check, and conditional pull for a single repository.
    Appends the repo name to the appropriate list.
    """
    try:
        run_git(['fetch'], repo_path, check=True)
        status_output = run_git(['status'], repo_path)
        print(status_output)
        if "nothing to commit, working tree clean" in status_output:
            run_git(['pull'], repo_path, check=True)
            clean_repos.append(repo_name)
        else:
            print("\nWARNING: Working tree not clean or has pending changes. Skipping 'git pull'")
            wip_repos.append(repo_name)
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

def _prompt_for_identity(repo_name, known_identities):
    """
    Prompts the user to select an existing identity or enter a new one.

    Args:
        repo_name (str): The name of the repository.
        known_identities (list): A list of (username, email) tuples.

    Returns:
        tuple: A (username, email) tuple for the repository.
    """
    print(f"\nNo complete user identity (name and email) set for '{repo_name}'.")

    if not known_identities:
        print("No existing identities found. Please enter a new one.")
        new_name = input("Enter user.name: ")
        new_email = input("Enter user.email: ")
        return new_name, new_email

    print("Please choose an identity:")
    for i, (name, email) in enumerate(known_identities):
        default_text = " (default, press Enter)" if i == 0 else ""
        print(f"  {i+1}: {name} <{email}>{default_text}")

    print("  N: Enter a new identity")

    while True:
        choice = input("Your choice: ").strip().lower()

        if not choice:  # Default to the most recent one
            return known_identities[0]

        if choice == 'n':
            new_name = input("Enter new user.name: ")
            new_email = input("Enter new user.email: ")
            return new_name, new_email

        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(known_identities):
                return known_identities[choice_idx]
            else:
                print(f"Invalid number. Please enter a number between 1 and {len(known_identities)}.")
        except ValueError:
            print("Invalid input. Please enter a number or 'n'.")

def update_repos():
    """
    Updates all local repos in the current directory with the logic from git-update.sh.
    """
    clean_repos = []
    wip_repos = []
    owner_mismatch_repos = []
    known_identities = []

    current_dir = os.getcwd()

    # Create global gitignore if it doesn't exist
    gitignore_path = os.path.expanduser("~/.gitignore_global")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, 'w') as f:
            f.write(".DS_Store\n")
        run_git(['config', '--global', 'core.excludesfile', gitignore_path], current_dir)
        print("Global .gitignore created and configured successfully")
    else:
        print("Global .gitignore file already exists. Skipping creation")

    for dir_name in os.listdir('.'):
        repo_path = os.path.join(current_dir, dir_name)
        if os.path.isdir(repo_path) and dir_name != '.' and '.git' in os.listdir(repo_path):
            print("\n" + "="*64)
            print(f"    CHECKING REPO: {dir_name}")
            print("="*64 + "\n")

            # Step 1: Check and set local user.name and email
            print("Step 1: check local user.name and email..")
            local_username = run_git(['config', '--local', 'user.name'], repo_path)
            local_email = run_git(['config', '--local', 'user.email'], repo_path)

            if not local_username or not local_email:
                new_username, new_email = _prompt_for_identity(dir_name, known_identities)
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
            remote_url = run_git(['config', '--get', 'remote.origin.url'], repo_path)
            repo_owner = get_repo_owner(remote_url)

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

            print(f"\nStep 3: fetch and pull (if clean) in {dir_name}..")
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
    parser.add_argument("-u", "--update", action="store_true", help="Update (fetch & pull) all local repos in the current directory")

    args = parser.parse_args()

    if args.list or args.clone_all:
        if args.username is None:
            parser.error("The 'username' argument is required for --list or --clone-all options")
        repos = list_github_repos(args.username)
        if repos is not None:
            if args.list:
                if repos:
                    for repo in repos:
                        print(f"{repo}")

            if args.clone_all:
                clone_or_pull_repos(args.username, repos)

    elif args.update or len(sys.argv) == 1:
        update_repos()

    else:
        parser.print_help()
