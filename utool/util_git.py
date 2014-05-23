#!/usr/bin/env python
from __future__ import absolute_import, division, print_function
import sys
import os
from itertools import izip
from os.path import exists, join, dirname, split, isdir
from ._internal import meta_util_git as mu  # NOQA
from ._internal.meta_util_git import get_repo_dirs, get_repo_dname  # NOQA
from . import util_inject
print, print_, printDBG, rrr, profile = util_inject.inject(__name__, '[git]')

repo_list = mu.repo_list

try:
    import __REPOS__
    PROJECT_REPOS = __REPOS__.PROJECT_REPOS
except ImportError:
    PROJECT_REPOS = []


def gitcmd(repo, command):
    print('')
    print("************")
    print(repo)
    os.chdir(repo)
    #if command.find('git') != 0:
    #    command = 'git ' + command
    os.system(command)
    print("************")


def gg_command(command):
    """ Runs a command on all of your PROJECT_REPOS """
    for repo in PROJECT_REPOS:
        print("GG: " + repo)
        if exists(repo):
            gitcmd(repo, command)


def checkout_repos(repo_urls, repo_dirs=None, checkout_dir=None):
    """ Checkout every repo in repo_urls into checkout_dir """
    # Check out any repo you dont have
    if checkout_dir is not None:
        repo_dirs = mu.get_repo_dirs(checkout_dir)
    assert repo_dirs is not None, 'specify checkout dir or repo_dirs'
    for repodir, repourl in izip(repo_dirs, repo_urls):
        print('[git] checkexist: ' + repodir)
        if not exists(repodir):
            mu.cd(dirname(repodir))
            mu.cmd('git clone ' + repourl)


def setup_develop_repos(repo_dirs):
    """ Run python installs """
    for repodir in repo_dirs:
        print('Installing: ' + repodir)
        mu.cd(repodir)
        assert exists('setup.py'), 'cannot setup a nonpython repo'
        mu.cmd('python setup.py develop')


def pull_repos(repo_dirs, repos_with_submodules=[]):
    for repodir in repo_dirs:
        print('Pulling: ' + repodir)
        mu.cd(repodir)
        assert exists('.git'), 'cannot pull a nongit repo'
        mu.cmd('git pull')
        reponame = split(repodir)[1]
        if reponame in repos_with_submodules or\
           repodir in repos_with_submodules:
            repos_with_submodules
            mu.cmd('git submodule init')
            mu.cmd('git submodule update')


def is_gitrepo(repo_dir):
    gitdir = join(repo_dir, '.git')
    return exists(gitdir) and isdir(gitdir)


if __name__ == '__main__':
    command = ' '.join(sys.argv[1:])
    # Apply command to all repos
    gg_command(command)
