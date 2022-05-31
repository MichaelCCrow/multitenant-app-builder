#!/usr/local/bin/python3
# A hard link to this exists within ome/dev/scripts

import argparse
import os
import sys
import glob
import subprocess
from multiprocessing import Pool
from loguru import logger as log

approot = '~/dev/projects/ome/app'
# projectroot = 'ome'
# appdir = 'app'

utildir = '../dev/utils'
menuscript = '~/bin/makemenu.sh'
selected = '/tmp/menuselect.val'

vue_cli_service = 'node_modules/.bin/vue-cli-service'

envs = ['local', 'dev', 'prod']

def tomcat_dest(tenant):
    return {
        'local': f'/usr/local/tomcat/webapps/{tenant}ome/',
        'dev': f'mcutomcat@esddrupal-dev:webapps/{tenant}ome/',
        'prod': f'mcutomcat@esddrupal-prod:webapps/{tenant}ome/'
    }

def errorexit(path=None, msg=None):
    if msg is None: log.error(f'could not find {path}')
    else: log.error(msg)
    sys.exit(1)

'''Verify and setup working directory.'''
def setup(wd):
    if os.getcwd() != wd:
        log.debug(f'changing working dir from [{os.getcwd()}] to project root: [{wd}]')

    if os.path.isdir(wd):
        os.chdir(wd)
        log.info(os.getcwd())

        if not os.path.isfile(vue_cli_service):
            errorexit(path='vue_cli_service')
        if not os.path.isdir(utildir):
            errorexit(path=utildir)

        global menuscript
        menuscript = os.path.join(utildir, os.path.basename(menuscript))
        if not os.path.isfile(menuscript):
            errorexit(path=menuscript)

        log.trace(menuscript)
    else:
        errorexit(msg=f'project root directory {wd} does not exist')

def set_arm_db():
    log.warning('replacing localhost with armdbdev in arm properties')
    armprop = 'src/main/resources/tenants/application-arm.properties'
    localdb = 'localhost:6543'
    remotedb = 'armdbdev:6543' # if env == 'dev' else 'armdbfoo:6543'
    from shutil import copyfile
    copyfile(armprop, armprop+'.bak')
    with open(armprop, 'r') as file:
        data = file.read().replace(localdb, remotedb)
    with open(armprop, 'w') as file:
        file.write(data)

def reset_arm_localdb():
    armprop = 'src/main/resources/tenants/application-arm.properties'
    from shutil import copyfile
    copyfile(armprop+'.bak', armprop)

def readselected():
    with open(selected, 'r') as f:
        return f.read()

def generatemenu(prompt, choices):
    print(prompt)
    cmd = [menuscript] + choices
    p = subprocess.Popen(cmd)
    p.communicate()
    return readselected()

def list_tenants():
    tenantconfigs = 'src/config/*[!global|!app]*.config.js'
    files = [file for file in glob.glob(tenantconfigs)]
    tenants = [os.path.basename(file).replace('.config.js', '') for file in files]
    log.debug(files); log.debug(tenants)
    return tenants


def collect_options(tenants, deploy, buildapi, no_api):
    log.info('collecting...')

    project = generatemenu('select project', ['all'] + tenants).strip()
    log.info(f'project selected::{project}')

    env = generatemenu('select build environment', envs).strip()
    log.info(f'selected environment::{env}')

    if not buildapi and not no_api:
        buildapi = generatemenu('deploy backend api?', ['no', 'yes']).strip() == 'yes'

    if not deploy and project != 'arm':
        dodeploy = False
        answer = input(f'Deploy to {env}? [Yy]\n')
        if answer == 'Y' and answer.isupper():
            dodeploy = True
            log.warning(f'Deploying to {env} for {project} project(s)')
        elif answer.lower() == 'y':
            answer = input('Confirm [Yy]')
            if answer.lower() == 'y':
                log.warning(f'[ACTION] Deploying to {env} for {project} project(s)')
                dodeploy = True
        else: log.info('only building')
    else:
        log.info('deploy flag provided')
        dodeploy = True

    return {
        'project': project,
        'env': env,
        'dodeploy': dodeploy,
        'buildapi': buildapi
    }

def deployapi(profile):
    log.info('building and deploying api...')
    os.chdir('..')
    if not os.path.isfile('pom.xml'):
        log.error(f'no pom.xml found in {os.getcwd()}')
        return
    cmd = ['mvn', '-P', profile, 'clean', 'install', 'tomcat7:redeploy']
    log.warning(f'[ACTION] {cmd}')
    subprocess.run(cmd)
    os.chdir('app')

def build(project):
    log.info('building...')
    if project in envs:
        deployapi(project)
        return
    else:
        cmd = ['npm', 'run', f'build:{project}']
        # if `npm run` doesn't work, try the following instead
        #os.environ['PROJECT_BUILD'] = project
        #cmd = [vue-cli-service, 'build']
        log.warning(f'[ACTION] {cmd}')
        subprocess.run(cmd)
        return

def deploy(tenant, env):
    src = os.path.join('dist', tenant, '')
    dest = tomcat_dest(tenant)[env]
    cmd = ['rsync', '-avz', '--delete', src, dest]
    log.warning(f'[ACTION] {cmd}')
    subprocess.run(cmd)

def getargs():
    parser = argparse.ArgumentParser(prog='multitenant-application-builder',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-a', '--app-dir', '--project-root', dest='project_root',
                        default=os.path.expanduser('~/dev/projects/ome/app'),
                        help='''Full path to the project's root directory containing node_modules and package.json''')
    parser.add_argument('-D', '--deploy', action='store_true',
                        help='Supply this flag to deploy the frontend UI. If not provided, confirmation must be given through a series of prompts.')
    parser.add_argument('-l', '--log', default='info',
                        choices=['trace', 'debug', 'info', 'warning', 'error', 'critical'],
                        help='Set a log level for debugging')
    apiopt = parser.add_argument_group('API Deploy Options').add_mutually_exclusive_group()
    apiopt.add_argument('-j', '--java', '--api-deploy', action='store_true',
                        help='''Supply this flag to build and deploy the backend API with maven [cannot be used with '-n']''')
    apiopt.add_argument('-n', '--no-api', action='store_true',
                        help='''Supply this flag to ignore building/deploying the API backend [cannot be used with '-j']''')
    # future_args = parser.add_argument_group('Not yet implemented')
    # future_args.add_argument('-A', '--all', action='store_true')
    # future_args.add_argument('-i', '--interactive', action='store_true')
    # future_args.add_argument('-p', '--project')
    return parser.parse_args(), parser

def main(args):
    log.remove()
    log.add(sink=sys.stderr, level=args.log.upper(),
            format=f'''{'<g>{time:YYYY-MM-DD HH:mm:ss!UTC}</g> | ' if args.log == 'debug' or args.log == 'trace' else ''}'''
                   + '<lvl>{level: <5}</lvl> | <lvl>{message}</lvl>')
    log.info('starting...')

    setup(args.project_root)
    tenants = list_tenants()

    options = collect_options(tenants, args.deploy, args.java, args.no_api)
    log.debug(options)

    project = options['project']
    env = options['env']
    buildapi = options['buildapi']

    if env != 'prod' and project != 'all' and project == 'arm':
        project += f':{env}'
        log.warning(f'Building for alternate ARM environent {project}')

    if project == 'all':
        if env != 'prod':
            for i, t in enumerate(tenants):
                if t == 'arm': tenants[i] += f':{env}'
        for t in tenants: log.warning(t)
        if buildapi: tenants += [env]
        with Pool(len(tenants)) as p:
            p.map(build, tenants)
    else: build(project)
    log.success('-------------------built---------------------')

    if options['dodeploy'] or args.deploy:
        log.info(f'deploying to {env}')
        if project == 'all':
            if buildapi: tenants.remove(env)
            for t in tenants:
                if ':' in t: t = t.split(':')[0]
                log.info(f'tenant:{t} :: env:{env}')
                deploy(tenant=t, env=env)
        else: deploy(tenant=project.split(':')[0], env=env)
        log.success('-------------------deployed---------------------')

if __name__ == '__main__':
    args, parser = getargs()
    main(args)
    sys.exit(0)
