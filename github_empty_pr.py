#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import tempfile
import subprocess
import shlex
import datetime

from apscheduler.schedulers.blocking import BlockingScheduler


HUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hub')


class GitHubRepo(object):

    def __init__(self, owner, repo):
        self.owner = owner
        self.repo = repo
        self.empty_prs = []
        tmpdir = tempfile.mkdtemp(suffix='github_repo')
        self.clone(cwd=tmpdir)
        self.repo_dir = os.path.join(tmpdir, repo)
        self.default_branch = self.get_current_branch()
        self.github_user = os.environ['GITHUB_USER']
        self.github_token = os.environ['GITHUB_TOKEN']
        self.setup_remote()

    def clone(self, cwd):
        cmd = 'git clone https://github.com/{0}/{1}.git'\
            .format(self.owner, self.repo)
        subprocess.call(shlex.split(cmd), cwd=cwd)

    def get_current_branch(self):
        cmd = 'git branch'
        output = subprocess.check_output(
            shlex.split(cmd), cwd=self.repo_dir).strip()
        for br in output.splitlines():
            if br.startswith('*'):
                return br.split()[-1]

    def setup_remote(self):
        url = 'https://{token}@github.com/{user}/{repo}.git'.format(
            user=self.github_user, token=self.github_token, repo=self.repo)
        cmd = 'git remote add {user} {url}'\
            .format(user=self.github_user, url=url)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)

    def check_ci_status(self, commit_sha):
        cmd = '{0} ci-status {1}'.format(HUB, commit_sha)
        output = subprocess.check_output(
            shlex.split(cmd), cwd=self.repo_dir).strip()
        return output

    def fetch_all(self):
        cmd = 'git fetch --all'
        subprocess(shlex.split(cmd), cwd=self.repo_dir)

    def commit_empty(self, branch, commit_msg):
        cmd = 'git checkout -b {0}'.format(branch)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)
        cmd = 'git commit --allow-empty -m "{0}"'.format(commit_msg)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)
        self.check_commit_sha()

    def check_commit_sha(self):
        cmd = 'git log -1 --format="%H"'
        commit_sha = subprocess.check_output(
            shlex.split(cmd), cwd=self.repo_dir).strip()
        return commit_sha

    def send_empty_pr(self):
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        # update cached remote branch
        self.fetch_all()
        cmd = 'git checkout origin/{0}'.format(self.default_branch)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)
        # empty commit
        branch = 'empty-commit-{0}'.format(timestamp)
        commit_msg = 'Empty commit for Travis test at {0}'.format(timestamp)
        commit_sha = self.commit_empty(branch, commit_msg)
        # push
        cmd = 'git push {0} {1}'.format(self.github_user, branch)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)
        # send pull request
        cmd = '{0} pull-request -m "{1}" -h {2}:{3} -b {4}:{5}'\
            .format(HUB, commit_msg, self.github_user, branch,
                    self.owner, self.default_branch)
        subprocess.call(shlex.split(cmd), cwd=self.repo_dir)
        self.empty_prs.append((branch, commit_sha))

    def close_ci_success_empty_pr(self):
        for br, sha in self.empty_prs:
            if self.check_ci_status(sha) == 'success':
                cmd = 'git push {0} {1} --delete'.format(self.github_user, br)
                subprocess.call(shlex.split(cmd), cwd=self.repo_dir)


class GitHubReposHandler(object):

    def __init__(self, repo_slugs):
        self.gh_repos = []
        for slug in repo_slugs:
            owner, repo = slug.split('/')
            self.gh_repos.append(GitHubRepo(owner, repo))

    def send_empty_pr(self):
        for repo in self.gh_repos:
            repo.send_empty_pr()

    def close_ci_success_empty_pr(self):
        for repo in self.gh_repos:
            repo.close_ci_success_empty_pr()


def main():
    repo_slugs = ['start-jsk/jsk_apc']
    gh_repos_handler = GitHubReposHandler(repo_slugs)
    scheduler = BlockingScheduler()
    scheduler.add_job(gh_repos_handler.send_empty_pr,
                      trigger='interval', minutes=5)
    scheduler.add_job(gh_repos_handler.close_ci_success_empty_pr,
                      trigger='interval', minutes=5)
    scheduler.print_jobs()
    scheduler.start()


if __name__ == '__main__':
    main()