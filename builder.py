#!/usr/local/bin/python3

import argparse
import os
import sys
import glob
import subprocess
from multiprocessing import Pool

approot = '~/dev/projects/ome/app'
# projectroot = 'ome'
# appdir = 'app'

utildir = '../dev/utils'
menuscript = '~/bin/makemenu.sh'
selected = '/tmp/menuselect.val'

vue_cli_service = 'node_modules/.bin/vue-cli-service'
vcs_build_cmd = ['build', '--mode']

envs = ['local', 'dev', 'prod']

def tomcat_dest(tenant):
    return {
        'local': f'/usr/local/tomcat/webapps/{tenant}ome/',
        'dev': f'mcutomcat@esddrupal-dev:webapps/{tenant}ome/'
    }

def errorexit(path=None, msg=None):
    if msg is None: print(f'could not find {path}')
    else: print(msg)
    sys.exit(1)

'''Verify and setup working directory.'''
def setup(wd, verbose=False):

    # print(sys.argv[0])
    # projectdir = os.path.commonprefix([os.path.abspath(sys.argv[0]), os.getcwd()] )
    # print('projectdir:', projectdir)
    # if projectroot in projectdir:
    #     if projectdir.endswith(projectroot): pass
        # if verbose: print('cwd is project root')
        # else:
            # print(os.getcwd())
            # newdir = os.path.join(projectdir, appdir)
            # os.chdir(newdir)
            # os.chdir(appdir)
        # print(os.getcwd())
        # if verbose: print(os.getcwd())
    # else:
    #     print(f'must be in a sub directory of {projectroot}/')
    #     sys.exit(1)

    if verbose:
        print(os.getcwd())
        print(wd)

    if os.path.isdir(wd):
        os.chdir(wd)
        print('[INFO]', os.getcwd())

        if not os.path.isfile(vue_cli_service):
            errorexit(path='vue_cli_service')
        if not os.path.isdir(utildir):
            errorexit(path=utildir)

        global menuscript
        menuscript = os.path.join(utildir, os.path.basename(menuscript))
        if not os.path.isfile(menuscript):
            errorexit(path=menuscript)

        if verbose: print(menuscript)
    else:
        errorexit(msg=f'project root directory {wd} does not exist')


def readselected():
    with open(selected, 'r') as f:
        return f.read()

def generatemenu(prompt, choices):
    print(prompt)
    cmd = [menuscript] + choices
    p = subprocess.Popen(cmd)
    p.communicate()
    return readselected()

def list_tenants(verbose=False):
    tenantconfigs = 'src/config/*[!global|!arm|!app]*.config.js'
    files = [file for file in glob.glob(tenantconfigs)]
    tenants = [os.path.basename(file).replace('.config.js', '') for file in files]
    if verbose:
        print(files)
        print(tenants)
    return tenants


def collect_options(tenants, deploy, buildapi, no_api):
    print('[INFO] collecting...')

    project = generatemenu('select project', tenants + ['all']).strip()
    print(f'[INFO] project selected::{project}')

    env = generatemenu('select build environment', envs).strip()
    print(f'[INFO] selected environment::{env}')

    if not buildapi and not no_api:
        buildapi = generatemenu('deploy backend api?', ['yes', 'no']).strip() == 'yes'

    if not deploy:
        dodeploy = False
        answer = input(f'Deploy to {env}? [Yy]\n')
        if answer == 'Y' and answer.isupper():
            dodeploy = True
            print(f'Deploying to {env} for {project} project(s)')
        elif answer.lower() == 'y':
            answer = input('Confirm [Yy]')
            if answer.lower() == 'y':
                print(f'[ACTION] Deploying to {env} for {project} project(s)')
                dodeploy = True
        else: print('[INFO] only building')
    else:
        print('[INFO] deploy flag provided')
        dodeploy = True

    return {
        'project': project,
        'env': env,
        'dodeploy': dodeploy,
        'buildapi': buildapi
    }

def deployapi(profile):
    print('[INFO] building and deploying api...')
    os.chdir('..')
    if not os.path.isfile('pom.xml'):
        print(f'[ERROR] no pom.xml found in {os.getcwd()}')
        return
    cmd = ['mvn', '-P', profile, 'clean', 'install', 'tomcat7:redeploy']
    print('[ACTION]', cmd)
    subprocess.run(cmd)
    os.chdir('app')

def build(project):
    print('[INFO] building...')
    if project in envs:
        deployapi(project)
        return
    else:
        cmd = [vue_cli_service] + vcs_build_cmd + [project]
        print('[ACTION]', cmd)
        subprocess.run(cmd)
        return

def deploy(tenant, env):
    src = os.path.join('dist', tenant, '')
    dest = tomcat_dest(tenant)[env]
    cmd = ['rsync', '-avz', '--delete', src, dest]
    print('[ACTION]', cmd)
    subprocess.run(cmd)

def getargs():
    parser = argparse.ArgumentParser(
        prog='multitenant-application-builder',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-a', '--app-dir', dest='project_root',
                        default=os.path.expanduser('~/dev/projects/ome/app'),
                        help='''Full path to the project's root directory containing node_modules and package.json''')
    parser.add_argument('-A', '--all', action='store_true', default=False)
    parser.add_argument('-i', '--interactive', action='store_true', default=False)
    parser.add_argument('-D', '--deploy', action='store_true', default=False)
    parser.add_argument('-j', '--java', action='store_true', default=False)
    parser.add_argument('-n', '--no-api', action='store_true', default=False)
    parser.add_argument('-p', '--project', required=False)
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    return parser.parse_args(), parser

def main(args, parser):
    print('[INFO] starting...')
    if args.java and args.no_api:
        print('[WARN] Both -n and -j options cannot be used together.')
        parser.print_help()
        sys.exit(1)


    setup(args.project_root, args.verbose)
    tenants = list_tenants()

    options = collect_options(tenants, args.deploy, args.java, args.no_api)
    if args.verbose: print(options)

    project = options['project']
    env = options['env']
    buildapi = options['buildapi']

    if project == 'all':
        if buildapi: tenants += [env]
        with Pool(len(tenants)) as p:
            p.map(build, tenants)
    else: build(project)
    print('-------------------built---------------------')

    if options['dodeploy'] or args.deploy:
        print(f'deploying to {env}')
        if project == 'all':
            if buildapi: tenants.remove(env)
            for t in tenants:
                deploy(tenant=t, env=env)
        else: deploy(tenant=project, env=env)
        print('-------------------deployed---------------------')

if __name__ == '__main__':
    args, parser = getargs()
    main(args, parser)
    sys.exit(0)
