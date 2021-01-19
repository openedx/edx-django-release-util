#!/usr/bin/env python
import os
import os.path
import logging
import subprocess
import fileinput
import tempfile
import shutil

import click
import github3

logging.basicConfig(level=logging.INFO)

# List of owner/repository in which to look for/change the package version.
REPOS_TO_CHANGE = (
    ('edx', 'credentials'),
    ('edx', 'course-discovery'),
    ('edx', 'ecommerce'),
    ('edx', 'programs'),
    ('edx', 'edx-analytics-data-api'),
    ('edx', 'edx-analytics-dashboard'),
    ('edx', 'xqueue'),
    ('edx', 'edx-platform'),
)

# Format to convert the repos above to an HTTPS url.
REPO_URL_FORMAT = 'https://github.com/{}/{}'



class GitHubApiUtils:
    """
    Class to query/set GitHub info.
    """
    def __init__(self, owner, repo_name):
        """
        Returns a GitHub object, possibly authed as a user.
        """
        token = os.environ.get('GITHUB_TOKEN', '')
        if len(token):
            self.gh = github3.login(token=token)
        else:
            self.gh = github3.GitHub()
        self.repo = self.gh.repository(owner, repo_name)

    def create_pull(self, *args, **kwargs):
        return self.repo.create_pull(*args, **kwargs)


@click.command()
@click.option("--module_name", help="Name of Python module which is being updated.", type=str, required=True)
@click.option("--new_version", help="Updated version of Python module.", type=str, required=True)
@click.option("--local_only", help="Modify local repo branch without pushing to -or- creating PR on remote.", is_flag=True, default=False)
def bump_repos_version(module_name, new_version, local_only):
    """
    Changes the pinned version number in the requirements files of all repos
    which have the specified Python module as a dependency.

    This script assumes that GITHUB_TOKEN is set for GitHub authentication.
    """
    # Make the cloning directory and change directories into it.
    tmp_dir = tempfile.mkdtemp(dir=os.getcwd())

    # Iterate through each repository.
    for owner, repo_name in REPOS_TO_CHANGE:
        repo_url = REPO_URL_FORMAT.format(owner, repo_name)

        gh = GitHubApiUtils(owner, repo_name)

        os.chdir(tmp_dir)

        # Clone the repo.
        ret_code = subprocess.call(['git', 'clone', f'{repo_url}.git'])
        if ret_code:
            logging.error('Failed to clone repo {}'.format(repo_url))
            continue

        # Change into the cloned repo dir.
        os.chdir(repo_name)

        # Create a branch, using the version number.
        branch_name = f'{module_name}/{new_version}'
        ret_code = subprocess.call(['git', 'checkout', '-b', branch_name])
        if ret_code:
            logging.error('Failed to create branch in repo {}'.format(repo_url))
            continue

        # Search through all TXT files to find all lines with the module name, changing the pinned version.
        files_changed = False
        for root, _dirs, files in os.walk('.'):
            for file in files:
                if file.endswith('.txt') and (('requirements' in file) or ('requirements' in root)):
                    found = False
                    filepath = os.path.join(root, file)
                    with open(filepath) as f:
                        if f'{module_name}==' in f.read():
                            found = True
                    if found:
                        files_changed = True
                        # Change the file in-place.
                        for line in fileinput.input(filepath, inplace=True):
                            if f'{module_name}==' in line:
                                print(f'{module_name}=={new_version}')
                            else:
                                print(line, end=' ')

        if not files_changed:
            # Module name wasn't found in the requirements files.
            logging.info("Module name '{}' not found in repo {} - skipping.".format(module_name, repo_url))
            continue

        # Add/commit the files.
        ret_code = subprocess.call(['git', 'commit', '-am', f'Updating {module_name} requirement to version {new_version}'])
        if ret_code:
            logging.error("Failed to add and commit changed files to repo {}".format(repo_url))
            continue

        if local_only:
            # For local_only, don't push the branch to the remote and create the PR - leave all changes local for review.
            continue

        # Push the branch.
        ret_code = subprocess.call(['git', 'push', '--set-upstream', 'origin', branch_name])
        if ret_code:
            logging.error("Failed to push branch {} upstream for repo {}".format(branch_name, repo_url))
            continue

        # Create a PR with an automated message.
        rollback_branch_push = False
        try:
            # The GitHub "mention" below does not work via the API - unfortunately...
            response = gh.create_pull(
                title=f'Change {module_name} version.',
                body=f'Change the required version of {module_name} to {new_version}.\n\n@edx-ops/pipeline-team Please review and tag appropriate parties.',
                head=branch_name,
                base='master'
            )
        except:
            logging.error('Failed to create PR for repo {} - did you set GITHUB_TOKEN?'.format(repo_url))
            rollback_branch_push = True
        else:
            logging.info('Created PR #{} for repo {}: {}'.format(response.number, repo_url, response.html_url))

        if rollback_branch_push:
            # Since the PR creation failed, delete the branch in the remote repo as well.
            ret_code = subprocess.call(['git', 'push', 'origin', '--delete', branch_name])
            if ret_code:
                logging.error("ROLLBACK: Failed to delete upstream branch {} for repo {}".format(branch_name, repo_url))

    if not local_only:
        # Remove the temp directory containing all the cloned repos.
        shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    bump_repos_version()
