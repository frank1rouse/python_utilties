#!/usr/bin/python
'''
Created on Apr 10, 2017

@author: rousef
'''
import os
import sys
import time
import argparse
import github3
import platform
import subprocess
from ConfigParser import ConfigParser
from chainmap import  ChainMap
from StringIO import StringIO
from github3.repos import repo

# In order to better use this program store your credentials in the git hub store.
# Follow the list of commands below.
# 
# The clone command will prompt you for credentials for github. The config command
# will save the credentials in the git global store
# 
# 
# git clone https://github.com/dellemc-symphony/vcenter-adapter-parent.git
# git config --global credential.helper store
# 
# git clone https://eos2git.cec.lab.emc.com/VCE-Symphony/connect-home-service.git
# git config --global credential.helper store
# 
# If you are on a shared machine put a timeout on how long git will cache the credentials like below
# git config --global credential.helper 'cache --timeout=3600'

def getArguments():
    # Program Internal settings
    # I know that it is slower to load this way but it is more explicit and readable in my opinion
    program_defaults = {}
    program_defaults['github_url']           = 'https://github.com'
    program_defaults['github_organization']  = 'dellemc-symphony'
    program_defaults['giteos2_url']          = 'https://eos2git.cec.lab.emc.com'
    program_defaults['giteos2_organization'] = 'VCE-Symphony'
    program_defaults['giteos2_certs']        = '/opt/security/EMC_CA_GIT_HUB_Combo.pem'
    program_defaults['root_parent_version']  = '1.1.0'
    program_defaults['git_branch']           = 'master'

    # Property File settings
    property_file_name = os.path.splitext(os.path.basename(__file__))[0] + '.props'
    property_file_path = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(property_file_name))) + os.sep + property_file_name
    property_file_properties = {}
    #If no property file exists, don't sweat it just keep going.
    try:
        config = ConfigParser()
        with open(property_file_path) as stream:
            stream = StringIO("[root]\n" + stream.read())
        config.readfp(stream)
        property_file_properties =  dict(config.items('root'))
    except IOError:
        pass

    # Command Line settings
    parser = argparse.ArgumentParser()
    parser.add_argument('-gu', '--github_username',         help='User name associated with Github account.')
    parser.add_argument('-gp', '--github_password',         help='Password associated with Github account')
    parser.add_argument('-gt', '--github_authtoken',        help='Authentication token associated with Github account.')
    parser.add_argument('-go', '--github_organization',     help='Github source organization. Default: ' + program_defaults['github_organization'])
    parser.add_argument('-eos2url', '--giteos2_url',        help='eos2 git URL. Default: ' + program_defaults['giteos2_url'])
    parser.add_argument('-eos2u', '--giteos2_username',     help='User name associated with eos2 account.')
    parser.add_argument('-eos2p', '--giteos2_password',     help='Password associated with eos2 account')
    parser.add_argument('-eos2t', '--giteos2_authtoken',    help='Authentication token associated with eos2 account.')
    parser.add_argument('-eos2o', '--giteos2_organization', help='eos2 source organization. Default: ' + program_defaults['giteos2_organization'])
    parser.add_argument('-rpv', '--root_parent_version',    help='The root-parent version used in the generated maven parent pom.xml.')
    parser.add_argument('-gb', '--git_branch',              help='The git branch that should be checkout in each repository.')
    namespace = parser.parse_args()
    # Create a dictionary of the given parser command line inputs
    command_line_args = {k:v for k,v in vars(namespace).items() if v}
    
    # Now create a chainmap of all the dictionaries in the order of precedence.
    return ChainMap(command_line_args, os.environ, property_file_properties, program_defaults)

def gitHubConnect(args):
    try:
        # If given use the authentication token
        if 'github_authtoken' in args:
            gh = github3.login(token=args['github_authtoken'])
        else:
            gh = github3.login(username=args['github_username'], password=args['github_password'])
        # Log into the organization used by this operation.
        gh.organization(args['github_organization'])
    except: 
        print 'Unable to login with given credentials.'
        if 'github_authtoken' in args:
            print 'Github authentication token = "{}"'.format(args['github_authtoken'])
        else:
            print 'Github user name            = "{}"'.format(args['github_username'])
            print 'Github password             = "{}"'.format(args['github_password'])
        print 'Github organization         = "{}"'.format(args['github_organization'])
        exit(1)
    return gh

def gitEnterpriseConnect(args):
    try:
        # If given use the authentication token
        if 'giteos2_authtoken' in args:
            ghe = github3.GitHubEnterprise(url=args['giteos2_url'], token=args['giteos2_authtoken'], verify=args['giteos2_certs'])
        else:
            ghe = github3.GitHubEnterprise(url=args['giteos2_url'], username=args['giteos2_username'], password=args['giteos2_password'], verify=args['giteos2_certs'])
        # Log into the organization used by this operation.
        ghe.organization(args['giteos2_organization'])
    except:
        print 'Unable to login with given credentials.'
        print 'Github Enterprise url                  = "{}"'.format(args['giteos2_url'])
        if 'giteos2_authtoken' in args:
            print 'Github Enterprise authentication token = "{}"'.format(args['giteos2_authtoken'])
        else:
            print 'Github Enterprise user name            = "{}"'.format(args['giteos2_username'])
            print 'Github Enterprise password             = "{}"'.format(args['giteos2_password'])
        print 'Github Enterprise organization         = "{}"'.format(args['giteos2_organization'])
        exit(1)
    return ghe

def getOrgRepos(gh, organization):
    strip_space = len(organization) + 1
    org = gh.organization(login=organization)
    repos = []
    for repo in org.iter_repos(type='all'):
        bare_repo_name = str(repo)[strip_space:]
        if bare_repo_name.startswith('rcm'):
            repos.append(str(repo)[strip_space:])
    return sorted(repos)

def getUserRepos(gh, organization):
    strip_space = len(organization) + 1
    user_repos = gh.iter_user_repos(login='rousef')
    repos = []
    for repo in user_repos:
        bare_repo_name = str(repo)[strip_space:]
        if bare_repo_name.startswith('rcm'):
            repos.append(str(repo)[strip_space:])
    return sorted(repos)

def clone_or_update_repos(repos, organization, url, branch):
    maven_repos = []
    cmd_sep = ';'
    if platform.system() == 'Windows':
        cmd_sep = '&'
        
    for repo in repos:
        repo = repo.strip()
        if os.path.isdir(repo):
            print 'Pulling updates into repo {}'.format(repo)
            sys.stdout.flush()
            git_command = 'cd {} {cmd_sep} git pull'.format(repo, cmd_sep=cmd_sep)
        else:
            print 'Cloning repo {}'.format(repo)
            sys.stdout.flush()
            git_command = 'git clone {}/{}/{}.git'.format(url, organization, repo)

#         git_command = '{} {cmd_sep} cd {repo} {cmd_sep} git checkout {branch} {cmd_sep} cd ..'.format(git_command, repo=repo, cmd_sep=cmd_sep, branch=branch)

        p = subprocess.Popen(git_command, stdout=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()
        if p.returncode != 0:
            return -1

        git_command = 'cd {repo} {cmd_sep} git checkout {branch}'.format(repo=repo, cmd_sep=cmd_sep, branch=branch )
        p = subprocess.Popen(git_command, stdout=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()
        if p.returncode != 0:
            # Not such a big deal that the command failed. Print out a warning and move on.
            print 'Repo {} does contain the branch "{}"'.format(repo, branch)

        if os.path.exists('{}/pom.xml'.format(repo)):
            maven_repos.append(repo)
        print '--------------------------------------------------------------------------------'
        sys.stdout.flush()
    return maven_repos

def write_parent_pom(maven_repo_list, root_parent_version):
    # Save older versions of the pom for comparison later
    if 'pom.xml' in os.listdir('.'):
        timestamp = 'pom_{}.xml'.format(time.strftime('%Y-%m-%d_%H_%M_%S'))
        os.rename('pom.xml', timestamp) 
    pom = open('pom.xml', 'w')
    pom.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    pom.write('<project xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
    pom.write('     xmlns="http://maven.apache.org/POM/4.0.0"\n')
    pom.write('     xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">\n')
    pom.write('\n')
    pom.write('    <parent>\n')
    pom.write('        <groupId>com.dell.cpsd</groupId>\n')
    pom.write('        <artifactId>root-parent</artifactId>\n')
    pom.write('        <version>{}</version>\n'.format(root_parent_version))
    pom.write('    </parent>\n')
    pom.write('\n')
    pom.write('    <groupId>com.dell.cpsd</groupId>\n')
    pom.write('    <artifactId>github-dependency-calculator</artifactId>\n')
    pom.write('    <modelVersion>4.0.0</modelVersion>\n')
    pom.write('    <packaging>pom</packaging>\n')
    pom.write('    <version>1.0-SNAPSHOT</version>\n')
    pom.write('    <name>GitHub Dependency Calculator</name>\n')
    pom.write('\n')
    pom.write('    <modules>\n')
    for repo in maven_repo_list:
        pom.write('        <module> {} </module>\n'.format(repo))
    pom.write('    </modules>\n')
    pom.write('\n')
    pom.write('</project>\n')
    pom.close()

def main():

    args = getArguments()
    # This is an abandoned repository that no longer builds
    excluded_maven_repos = ['engineering-standards-services']
    # Example repositories not meant to be built as part of the standard build.
    excluded_maven_repos += ['hello-world-docker-example', 'hello-world-usecase-rpm']

    # Create a list of all of the github repositories
    github_repos = []
    github_source = gitHubConnect(args)
    strip_space = len(args['github_organization']) + 1
    github_org = github_source.organization(args['github_organization'])
    for repo in github_org.iter_repos(type='all'):
        github_repos.append(str(repo)[strip_space:])
    github_repos = sorted(github_repos)

    # Create a list of all of the eos2 repositories
    # Eliminate repositories that have already been moved to github
    eos2_repos = []
    eos2_source = gitEnterpriseConnect(args)
    strip_space = len(args['giteos2_organization']) + 1
    eos2_org = eos2_source.organization(args['giteos2_organization'])
    for repo in eos2_org.iter_repos(type='all'):
        repo = str(repo)[strip_space:]
        if repo not in github_repos:
            eos2_repos.append(repo)
    eos2_repos = sorted(eos2_repos)

    print '********************************************************************************'
    print '********************************************************************************'
    print 'Cloning/Updating github repositories'
    print '********************************************************************************'
    print '********************************************************************************'
    maven_repos = clone_or_update_repos(repos=github_repos, organization=args['github_organization'], url=args['github_url'], branch=args['git_branch'])
    print '********************************************************************************'
    print '********************************************************************************'
    print 'Cloning/Updating eos2 repositories'
    print '********************************************************************************'
    print '********************************************************************************'
    maven_repos = maven_repos + clone_or_update_repos(repos=eos2_repos, organization=args['giteos2_organization'], url=args['giteos2_url'], branch=args['git_branch'])
    maven_repos = sorted(maven_repos)
    print '\n'
    # Remove the repos we know will not build
    for repo in excluded_maven_repos:
        print 'Removing repo "{}" from the maven parent build configuration.'.format(repo)
        try:
            maven_repos.remove(repo)
        except:
            print 'Repo "{}" is not part of the maven parent build configuration'.format(repo)
            pass
    write_parent_pom(maven_repo_list=maven_repos, root_parent_version=args['root_parent_version'])


if __name__ == '__main__':
    start_time = time.time()
    start_clock = time.clock()
    main()
    print('--- {} seconds ---').format((time.time() - start_time))
    print('--- {} clock seconds ---').format((time.clock() - start_clock))
