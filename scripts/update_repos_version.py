#!/usr/bin/env python
import os
import os.path
import re
import logging
import subprocess
import fileinput
import shutil
import click
import github

LOG_FILENAME = 'bump_repo_version_log.txt'
logging.basicConfig(filename=LOG_FILENAME,level=logging.INFO)


REPOS_TO_CHANGE = (
    'https://github.com/edx/credentials.git',
    'https://github.com/edx/course-discovery.git',
    'https://github.com/edx/ecommerce.git',
    'https://github.com/edx/programs.git',
    'https://github.com/edx/edx-analytics-data-api.git',
    'https://github.com/edx/edx-analytics-dashboard.git',
    'https://github.com/edx/xqueue.git',
    'https://github.com/edx/edx-platform.git',
)

# Here's where we'll clone the repos.
TEMP_DIRECTORY = 'git_tmp'

RELEASE_UTIL_REPO_NAME = 'edx-django-release-util'


class GitHubApiUtils(object):
    """
    Class to query/set GitHub info.
    """
    def __init__(self, repo_id):
        """
        Returns a GitHub object, possibly authed as a user.
        """
        token = os.environ.get('GITHUB_TOKEN', '')
        username = os.environ.get('GITHUB_USERNAME', '')
        password = os.environ.get('GITHUB_PASSWORD', '')
        if len(token):
            self.gh = github.Github(login_or_token=token)
        elif len(username) and len(password):
            self.gh = github.Github(login_or_token=username, password=password)
        else:
            # No auth available - use the API anonymously.
            self.gh = github.Github()
        self.repo = self.gh.get_repo(repo_id)

    def create_pull(self, *args, **kwargs):
        return self.repo.create_pull(*args, **kwargs)


@click.command()
@click.option("--new_version", help="New version of edx-django-release-util.", type=str, required=True)
def bump_repos_version(new_version):
    """
    Changes the pinned version number in the requirements files of all repos
    which have edx-django-release-util as a dependency.

    This script assumes the following environment variables are set for GitHub authentication:
    Either: GITHUB_TOKEN -or- GITHUB_USERNAME & GITHUB_PASSWORD.
    """
    # Make the cloning directory and change directories into it.
    original_dir = os.getcwd()
    if not os.path.exists(TEMP_DIRECTORY):
        os.makedirs(TEMP_DIRECTORY)
    os.chdir(TEMP_DIRECTORY)
    tmp_dir = os.getcwd()

    # Iterate through each repository.
    for repo in REPOS_TO_CHANGE:
        repo_pattern = re.compile(r'^https://github.com/edx/(.+).git$')
        repo_name = repo_pattern.match(repo).groups()[0]

        gh = GitHubApiUtils('edx/{}'.format(repo_name))

        # Clone the repo.
        ret_code = subprocess.call(['git', 'clone', repo])
        if ret_code:
            err_msg = "Failed to clone repo {}".format(repo)
            logging.error(err_msg)
            raise Exception(err_msg)

        # Change into the cloned repo dir.
        os.chdir(repo_name)

        # Create a branch, using the version number.
        branch_name = '{}/{}'.format(RELEASE_UTIL_REPO_NAME, new_version)
        ret_code = subprocess.call(['git', 'checkout', '-b', branch_name])
        if ret_code:
            err_msg = "Failed to create branch in repo {}".format(repo)
            logging.error(err_msg)
            raise Exception(err_msg)

        # Search through all TXT files to find all lines with edx-django-release-util, changing the pinned version.
        for root, dirs, files in os.walk('.'):
            for file in files:
                if file.endswith('.txt'):
                    found = False
                    filepath = os.path.join(root, file)
                    with open(filepath) as f:
                        if '{}=='.format(RELEASE_UTIL_REPO_NAME) in f.read():
                            found = True
                    if found:
                        # Change the file in-place.
                        for line in fileinput.input(filepath, inplace=True):
                            if '{}=='.format(RELEASE_UTIL_REPO_NAME) in line:
                                print '{}=={}'.format(RELEASE_UTIL_REPO_NAME, new_version)
                            else:
                                print line,

        # Add/commit the files.
        ret_code = subprocess.call(['git', 'commit', '-am', 'Updating {} requirement to version {}'.format(RELEASE_UTIL_REPO_NAME, new_version)])
        if ret_code:
            err_msg = "Failed to add and commit changed files to repo {}".format(repo)
            logging.error(err_msg)
            raise Exception(err_msg)

        # Push the branch.
        ret_code = subprocess.call(['git', 'push', '--set-upstream', 'origin', branch_name])
        if ret_code:
            err_msg = "Failed to push branch {} upstream for repo {}".format(branch_name, repo)
            logging.error(err_msg)
            raise Exception(err_msg)

        # Create a PR with an automated message.
        try:
            response = gh.create_pull(
                title='Change {} version.'.format(RELEASE_UTIL_REPO_NAME),
                body='Change the required version of {} to {}.\n\n@edx-ops/pipeline-team Please review and tag appropriate parties.'.format(RELEASE_UTIL_REPO_NAME, new_version),
                head=branch_name,
                base='master'
            )
        except UnknownObjectException:
            logging.error('No GitHub PR-creating permissions - did you set GITHUB_TOKEN or GITHUB_USERNAME/PASSWORD?')
        except:
            logging.error('Failed to create PR for repo {}!'.format(repo))
        else:
            logging.info('Created PR for repo {}: {}'.format(repo, response.html_url))

        # Change directory back up to tmp directory.
        os.chdir(tmp_dir)

    # Change directory back to script level and delete the temp git-cloning directory.
    os.chdir(original_dir)
    shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    bump_repos_version()
