#!/usr/bin/python
'''
Created on Nov 13, 2017

@author: rousef
'''

import os
import re
import sys
import json
import stat
import time
import shutil
import argparse
import platform
import subprocess
from glob import glob
from chainmap import  ChainMap
from StringIO import StringIO
from ConfigParser import ConfigParser

debug = False

# This utility script will not work without the following utilities available from the command line.
# git  - Nothing particular about the version.
# curl - Again nothing particular about the version
# hub  - Command line utility from github that allows you to create pull requests from the command line.
#        Available from https://github.com/github/hub
#
#
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


FILE_TIMESTAMP_FORMAT = '%Y-%m-%d_%H_%M_%S'
REPORT_GENERATED_TIME=time.strftime(FILE_TIMESTAMP_FORMAT)

def getArguments():
    # Program Internal settings
    # I know that it is slower to load this way but it is more explicit and readable in my opinion
    program_defaults = {}
    program_defaults['debug'] = 'False'
    program_defaults['group_id'] = 'com.dell.cpsd'
    program_defaults['maven_dependency_plugin_version'] = '3.0.2'
    program_defaults['dependency_tree_output_file'] = 'dependency_tree'

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
    parser.add_argument('-db',   '--debug',                           help='Ibid. Defaults to False')
    parser.add_argument('-gid',  '--group_id',                        help='Ibid. Defaults to com.dell.cpsd')
    parser.add_argument('-mpv',  '--maven_dependency_plugin_version', help='Ibid. Defaults to 3.0.2')
    parser.add_argument('-dtof', '--dependency_tree_output_file',     help='Ibid. Defaults to dependency_tree')
    namespace = parser.parse_args()
    # Create a dictionary of the given parser command line inputs
    command_line_args = {k:v for k,v in vars(namespace).items() if v}

    # Now create a chainmap of all the dictionaries in the order of precedence.
    return ChainMap(command_line_args, os.environ, property_file_properties, program_defaults)


def help():
    print '-db or   --debug                             Defaults to False'
    print '-mpv or  --maven_dependency_plugin_version   Defaults to 3.0.2'
    print '-gid or  --group_id                          Defaults to com.dell.cpsd'
    print '-dtof or --dependency_tree_output_file       Defaults to dependency_tree'
    print ''


# Add a parameter to choose if we should exit immediately on error.
# Default is we should exit if the parameter is not supplied.
def runExternalCommand(cmd, survive_error=False):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    if p.returncode != 0:
        print 'Error running command "{}"'.format(cmd)
        if output:
            print 'Standard output'
            lines = output.split('\n')
            for line in lines:
                print line
            sys.stdout.flush()
        if err:
            print ''
            print 'Error output'
            lines = err.split('\n')
            for line in lines:
                print line
            sys.stdout.flush()
        if not survive_error:
            exit(p.returncode)
    return (output, err)

def get_current_branch_head():
    (output, err) = runExternalCommand('git rev-parse HEAD')
    return output.strip()

def get_current_remote_url():
    (output, err) = runExternalCommand('git config --get remote.origin.url')
    return output.strip()

def get_maven_dirs(path):
    striped_directories=[]
    directories = glob(path + '*/')
    for directory in directories:
        # Strip all extraneous characters so we get only the directory names
        # Having an issue putting all of the regular expression matches in a single string.
        # Break them out for clarity as well as get around error
        directory = re.sub('\.', '', directory, count=1)
        directory = re.sub('\\\\', '', directory)
        directory = re.sub('/', '', directory)
        pom_file_path = directory + os.sep + 'pom.xml'
        if os.path.exists(pom_file_path):
            striped_directories.append(directory)
    return striped_directories

def get_all_files_named(matching_text, start_dir='.'):
    matching_files = []
    for root, dirs, files in os.walk(start_dir):
        for file in files:
            if file == matching_text:
                matching_files.append(os.path.join(root, file))
    return matching_files

def create_update_dependency_files(repositories, maven_dependency_plugin_version, dependency_tree_output):
    for repository in repositories:
        if debug:
            print ''
            print 'Working with repository {}'.format(repository)
            sys.stdout.flush()
        sha = ''
        old_sha = ''
        temp_repository_dependency_tree_file= ''
        repository_dependency_tree_file_name = repository + '.{}'.format(dependency_tree_output)
        temp_repository_dependency_tree_file_name = repository + '.{}.tmp'.format(dependency_tree_output)
        # Attempt to open the previous dependency file to compare sha values
        try:
            with open(repository_dependency_tree_file_name, 'r') as f:
                old_sha = f.readline().strip()
        except IOError:
            # Skip the error if the file isn't found.
            print 'No previous {} file exists. A new one will be created.'.format(repository_dependency_tree_file_name)
            sys.stdout.flush()

        if os.path.isfile(temp_repository_dependency_tree_file_name):
            print 'Removing previously temp file {} '.format(temp_repository_dependency_tree_file_name)
            sys.stdout.flush()
            os.remove(temp_repository_dependency_tree_file_name)

        with open(temp_repository_dependency_tree_file_name, 'w') as temp_repository_dependency_tree_file:
            # Go ahead and change into the repository directory.
            os.chdir(repository)
            # Grab the sha now once we are in the repository directory
            sha = get_current_branch_head()
            # Grab the remote url now that we are in the repository directory
            remote_url = get_current_remote_url()
            if old_sha:
                if sha == old_sha:
                    print 'Current sha is the same as {} file. No need to update the file.'.format( repository_dependency_tree_file_name)
                    sys.stdout.flush()
                    # Get us back to the top level directory
                    os.chdir('..')
                    temp_repository_dependency_tree_file.close()
                    os.remove(temp_repository_dependency_tree_file_name)
                    continue
                else:
                    print 'Current sha is different from {} file. The file will be updated.'.format(repository_dependency_tree_file_name)
                    sys.stdout.flush()
            # Write the sha as the first line of the dependency file.
            temp_repository_dependency_tree_file.write(sha + '\n')
            # Write the remote url as the second line of the dependency file.
            temp_repository_dependency_tree_file.write(remote_url + '\n')

            cmd = 'mvn org.apache.maven.plugins:maven-dependency-plugin:{}:tree -DoutputFile={}'.format(maven_dependency_plugin_version, dependency_tree_output)
            print 'Running command "{}"'.format(cmd)
            sys.stdout.flush()
            (output, err) = runExternalCommand(cmd)
            # Get all dependency files.
            dependency_files = get_all_files_named(dependency_tree_output)
            for dependency_file in dependency_files:
                with open(dependency_file, 'r') as f:
                    temp_repository_dependency_tree_file.write(f.read())
            # Reset the current directory.
            os.chdir('..')
        sys.stdout.flush()

        # If there exists a previous dependency file remove it
        if old_sha:
            os.remove(repository_dependency_tree_file_name)
        # Now rename the temp file to the dependency file name
        os.rename(temp_repository_dependency_tree_file_name, repository_dependency_tree_file_name)

def parse_artifact(artifact_line):
    artifact_info = artifact_line.split(':')
    group_id      = artifact_info[0]
    name          = artifact_info[1]
    type          = artifact_info[2]
    version       = artifact_info[3]
    phase = ''
    if len(artifact_info) > 4:
        phase = artifact_info[4]
    return group_id, name, type, version, phase

def read_dependency_info(repositories, dependency_tree_output, comparison_group_id):
    repositories_dependency_information = {}
    for repository in repositories:
        artifacts = []
        # Use a dictionary to store dependencies to eliminate duplicates
        group_dependencies = {}
        other_dependencies = {}
        group_dependencies_non_versioned = {}
        repository_dependency_tree_file_name = repository + '.{}'.format(dependency_tree_output)
        with open(repository_dependency_tree_file_name, 'r') as repository_dependency_tree_file:
            # Skip the sha line
            line = repository_dependency_tree_file.readline()
            # Skip the remote url line
            line = repository_dependency_tree_file.readline()
            line = repository_dependency_tree_file.readline().strip()
            while line:
                if line.startswith(comparison_group_id):
                    artifacts.append(line)
                else:
                    # Remove the visual characters from the line.
                    # I have had some issues when I group regular expressions so I'm going to do them one at a time.
                    line = re.sub('\+',   '', line)
                    line = re.sub('-',    '', line, 1) # Sub only the first dash to avoid to renaming artifacts
                    line = re.sub(' ',    '', line)
                    line = re.sub('\|',   '', line)
                    line = re.sub('\\\\', '', line)
                    group_id, name, type, version, phase = parse_artifact(line)
                    # Eliminate the phase entry as we are not really interested in it
                    new_artifact_entry = {'group_id': group_id, 'name': name, 'type': type, 'version': version, 'phase': phase}
                    # I could compare against group_id but there are still artifacts in which the group id is not correct.
                    if line.startswith(comparison_group_id):
                        group_dependencies[group_id + ':' + name + ':' + type + ':' + version] = new_artifact_entry
                        group_dependencies_non_versioned[group_id + ':' + name] = new_artifact_entry
                    else:
                        other_dependencies[group_id + ':' + name + ':' + type + ':' + version] = new_artifact_entry
                line = repository_dependency_tree_file.readline().strip()
        # Special case multi module repositories where one module has dependencies on another within the same repository
        # They shouldn't end up in either group_dependencies or group_dependencies_non_version
        # This should remove them.
        for artifact in artifacts:
            group_id, name, type, version, phase = parse_artifact(artifact)
            for dependency_artifact, dependency_artifact_info in sorted(group_dependencies_non_versioned.iteritems()):
                if name == dependency_artifact_info['name']:
                    del group_dependencies_non_versioned[dependency_artifact]
                    break
            for dependency_artifact, dependency_artifact_info in sorted(group_dependencies.iteritems()):
                if name == dependency_artifact_info['name']:
                    del group_dependencies[dependency_artifact]
                    break
        repositories_dependency_information[repository] = {'artifacts': artifacts, 'group_dependencies': group_dependencies, 'group_dependencies_non_versioned': group_dependencies_non_versioned, 'other_dependencies': other_dependencies}
    return repositories_dependency_information


def update_artifacts_already_generated(artifacts_already_generated_by_previous_groups, artifacts):
    for artifact in artifacts:
        group_id, name, type, version, phase = parse_artifact(artifact)
        artifacts_already_generated_by_previous_groups[name] = 1
    return artifacts_already_generated_by_previous_groups


def find_next_group_of_dependents(artifacts_already_generated_by_previous_groups, repository_info):
    # List of repositories that have been identified as belonging to this current group.
    current_group_repositories = []
    # We are going to remove keys from the repository info so preserve the original and return the modified copy
    temp_repository_info = repository_info
    # We are going to add artifacts to a copy of this dictionary and then copy the results at the end of the loop
    temp_artifacts_already_generated_by_previous_groups = artifacts_already_generated_by_previous_groups
    # If this routine is hit for the first time there will be no artifacts from previous groups. Use this as a flag for the first run.
    previously_run = True
    if not artifacts_already_generated_by_previous_groups:
        previously_run = False
    for repository, dependency_info in sorted(temp_repository_info.iteritems()):
        if debug:
            print 'Working with repository {}'.format(repository)
            sys.stdout.flush()
        # Special case for the first group with no group dependencies
        if not previously_run:
            if not dependency_info['group_dependencies_non_versioned']:
                if debug:
                    print 'Repository {} is a stand alone repository with no internal dependencies.'.format(repository)
                    sys.stdout.flush()
                for artifact in dependency_info['artifacts']:
                    group_id, name, type, version, phase = parse_artifact(artifact)
                    artifacts_already_generated_by_previous_groups[name] = 1
                current_group_repositories.append(repository)
                del temp_repository_info[repository] 
        else:
            unfounded_dependencies = False
            for artifact, artifact_info in sorted(dependency_info['group_dependencies_non_versioned'].iteritems()):
                if not artifact_info['name'] in artifacts_already_generated_by_previous_groups:
                    if debug:
                        print 'Dependent artifact {} not found in previous groups of generated artifacts.'.format(artifact_info['name'])
                        print 'Skipping repository {} for this group'.format(repository)
                        print ''
                        sys.stdout.flush()
                    unfounded_dependencies = True
                    break
            if not unfounded_dependencies:
                temp_artifacts_already_generated_by_previous_groups = update_artifacts_already_generated(temp_artifacts_already_generated_by_previous_groups, dependency_info['artifacts'])
                current_group_repositories.append(repository)
                del temp_repository_info[repository] 
    # Add the changes to the artifacts generated as part of this group
    artifacts_already_generated_by_previous_groups = temp_artifacts_already_generated_by_previous_groups 
    return artifacts_already_generated_by_previous_groups, temp_repository_info, current_group_repositories


def create_non_version_dependency_groups(repository_dependency_info):
    group_num = 0
    previously_generated_artifacts = {}
    non_version_dependency_groups = []
    countdown_dependency_info = repository_dependency_info.copy()
    while countdown_dependency_info:
        if debug:
            print 'Previously Generated Artifacts = {}'.format(previously_generated_artifacts)
        previously_generated_artifacts, countdown_dependency_info, current_group_repositories = find_next_group_of_dependents(previously_generated_artifacts, countdown_dependency_info)
        print '--------------------------------------------------------------------------------'
        print 'group_num {} has {} repositories.'.format(group_num, len(current_group_repositories))
        print 'current_group_repositories = "{}"'.format(current_group_repositories)
        print '--------------------------------------------------------------------------------'
        sys.stdout.flush()
        non_version_dependency_groups.append(current_group_repositories)
        if not current_group_repositories:
            print '... Halting issue.'
            print ''
            print 'The following repositories cannot find dependencies in the artifacts that have already been processed.'
            print ''
            for repository, dependency_info in sorted(countdown_dependency_info.iteritems()):
                print '{}'.format(repository)
            break
        group_num += 1
    return non_version_dependency_groups

def create_html_list_header(html_file, title_text):
    html_file.write('<!DOCTYPE html>\n')
    html_file.write('<html>\n')
    html_file.write('<head>\n')
    html_file.write('<meta charset="ISO-8859-1">\n')
    html_file.write('<title>' + title_text + '</title>\n')
    html_file.write('<link rel="shortcut icon" href="table.png">')
    html_file.write('<style>\n')
    html_file.write('tr:nth-of-type(odd) {\n')
    html_file.write('background-color: lightgreen;\n')
    html_file.write('}\n')
    html_file.write('tr:nth-of-type(even) {\n')
    html_file.write('  background-color: #A3FF4B;\n')
    html_file.write('}\n')
    html_file.write('  .build_order_width {\n')
    html_file.write('    width: 110px;\n')
    html_file.write('  }\n')
    html_file.write('  .build_job_width {\n')
    html_file.write('    width: 320px;\n')
    html_file.write('  }\n')
    html_file.write('</style>\n')
    html_file.write('</head>\n')
    html_file.write('<body>\n')
    html_file.write('<h2 align="center">'+title_text+'</h2>\n')


def create_html_end_of_report(html_file):
    html_file.write('  <br>\n')
    html_file.write('  <br>\n')
    html_file.write('  <h4>Report created on ' + REPORT_GENERATED_TIME +'</h4>\n')
    html_file.write('</body>\n')
    html_file.write('</html>\n')


def create_non_version_dependency_groups_html_report(non_version_dependency_groups, dependency_tree_output_file):
    print ''
    title = 'Symphony Build Order'
    html_file_name = 'symphony_build_order.html'
    temp_html_file_name = html_file_name + '.tmp'
    # If a temporary version is leftover just delete and start from scratch.
    if os.path.exists(temp_html_file_name):
        os.remove(temp_html_file_name)
    with open(temp_html_file_name, 'w') as temp_html_file:
        create_html_list_header(temp_html_file, title)
        temp_html_file.write('  <table border=1>\n')
        temp_html_file.write('    <tbody>\n')
        group_num = 0
        for group in non_version_dependency_groups:
            temp_html_file.write('      <tr style="color: black; background: lightgray;">\n')
            temp_html_file.write('        <td>Build Group {}</td>'.format(group_num))
            temp_html_file.write('      </tr>\n')
            temp_html_file.write('      <tr>\n')
            for repository in group:
                sha= ''
                git_url = ''
                with open('{}.{}'.format(repository, dependency_tree_output_file), 'r') as f:
                    sha = f.readline().strip()
                    git_url = f.readline().strip()
                organization = git_url.split('/')[3]
                pipeline_build = ''
                if organization == 'VCE-Symphony':
                    pipeline_build ='http://ci-build.mpe.lab.vce.com:8080/job/vce-symphony/job/{}'.format(repository)
                else:
                    if re.match('^[a-c].*', repository):
                        pipeline_build = 'http://ci-build.mpe.lab.vce.com:8080/job/dellemc-symphony1/job/{}'.format(repository)
                    if re.match('^[d-h].*', repository):
                        pipeline_build = 'http://ci-build.mpe.lab.vce.com:8080/job/dellemc-symphony2/job/{}'.format(repository)
                    if re.match('^[i-q].*', repository):
                        pipeline_build = 'http://ci-build.mpe.lab.vce.com:8080/job/dellemc-symphony3/job/{}'.format(repository)
                    if re.match('^[r].*', repository):
                        pipeline_build = 'http://ci-build.mpe.lab.vce.com:8080/job/dellemc-symphony4/job/{}'.format(repository)
                    if re.match('^[s-z].*', repository):
                        pipeline_build = 'http://ci-build.mpe.lab.vce.com:8080/job/dellemc-symphony5/job/{}'.format(repository)
                temp_html_file.write('        <tr>\n'.format(repository))
                temp_html_file.write('        <td><a href="{}">{}</a></td>\n'.format(git_url, repository))
                temp_html_file.write('        <td><a href="{}">pipeline build</a></td>\n'.format(pipeline_build))
                temp_html_file.write('        </tr>\n'.format(repository))
            temp_html_file.write('      </tr>\n')
            group_num += 1
        temp_html_file.write('    </tbody>\n')
        temp_html_file.write('  </table>\n')
        create_html_end_of_report(temp_html_file)
    if os.path.exists(html_file_name):
        os.remove(html_file_name)
    os.rename(temp_html_file_name, html_file_name)

def main():
    # Lets pull all of the arguments at once to force an error early if not available.
    args = getArguments()
    # This parameter has a default so we can already pull that value without worrying about an exception
    debug                           = args['debug']
    group_id                        = args['group_id']
    dependency_tree_output_file     = args['dependency_tree_output_file']
    maven_dependency_plugin_version = args['maven_dependency_plugin_version']

    repositories = get_maven_dirs('./')
    print '... Creating/Updating dependency files.'
    print ''
    sys.stdout.flush()
    create_update_dependency_files(repositories, maven_dependency_plugin_version, dependency_tree_output_file)
    print ''
    print '... Dependency files created.'
    print ''
    print '... Parsing dependency information.'
    print ''
    sys.stdout.flush()
    repository_dependency_info = read_dependency_info(repositories, dependency_tree_output_file, group_id)
    print '... Dependency information parsed.'
    print ''
    print '... Create Symphony build order groups'
    print ''
    sys.stdout.flush()
    non_version_dependency_groups = create_non_version_dependency_groups(repository_dependency_info)
    print ''
    print '... Symphony build order groups created.'
    print ''
    print '... Create Symphony build order html page.'
    create_non_version_dependency_groups_html_report(non_version_dependency_groups, dependency_tree_output_file)
    print '... Symphony build order html page created.'
    print ''
    with open('symphony_dependency_order_data.json', 'w') as f:
        json.dump(repository_dependency_info, f, sort_keys = True, indent=2, ensure_ascii = False)
    exit(0)

if __name__ == '__main__':
    main()
