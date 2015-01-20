from __future__ import unicode_literals
from __future__ import absolute_import
from requests.exceptions import ConnectionError, SSLError
import errno
import logging
import os
import re
import yaml
import six

from ..project import Project
from ..service import ConfigError
from .docopt_command import DocoptCommand
from .utils import call_silently, is_mac, is_ubuntu
from .docker_client import docker_client
from . import verbose_proxy
from . import errors
from .. import __version__

log = logging.getLogger(__name__)


class Command(DocoptCommand):
    base_dir = '.'

    def dispatch(self, *args, **kwargs):
        try:
            super(Command, self).dispatch(*args, **kwargs)
        except SSLError, e:
            raise errors.UserError('SSL error: %s' % e)
        except ConnectionError:
            if call_silently(['which', 'docker']) != 0:
                if is_mac():
                    raise errors.DockerNotFoundMac()
                elif is_ubuntu():
                    raise errors.DockerNotFoundUbuntu()
                else:
                    raise errors.DockerNotFoundGeneric()
            elif call_silently(['which', 'boot2docker']) == 0:
                raise errors.ConnectionErrorBoot2Docker()
            else:
                raise errors.ConnectionErrorGeneric(self.get_client().base_url)

    def perform_command(self, options, handler, command_options):
        if options['COMMAND'] == 'help':
            # Skip looking up the compose file.
            handler(None, command_options)
            return

        if 'FIG_FILE' in os.environ:
            log.warn('The FIG_FILE environment variable is deprecated.')
            log.warn('Please use COMPOSE_FILE instead.')

        explicit_config_path = options.get('--file') or os.environ.get('COMPOSE_FILE') or os.environ.get('FIG_FILE')
        project = self.get_project(
            self.get_config_path(explicit_config_path),
            project_name=options.get('--project-name'),
            verbose=options.get('--verbose'))

        handler(project, command_options)

    def get_client(self, verbose=False):
        client = docker_client()
        if verbose:
            version_info = six.iteritems(client.version())
            log.info("Compose version %s", __version__)
            log.info("Docker base_url: %s", client.base_url)
            log.info("Docker version: %s",
                     ", ".join("%s=%s" % item for item in version_info))
            return verbose_proxy.VerboseProxy('docker', client)
        return client

    def get_config(self, config_path):
        try:
            with open(config_path, 'r') as fh:
                return yaml.safe_load(fh)
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise errors.ComposeFileNotFound(os.path.basename(e.filename))
            raise errors.UserError(six.text_type(e))

    def get_project(self, config_path, project_name=None, verbose=False):
        try:
            return Project.from_config(
                self.get_project_name(config_path, project_name),
                self.get_config(config_path),
                self.get_client(verbose=verbose))
        except ConfigError as e:
            raise errors.UserError(six.text_type(e))

    def get_project_name(self, config_path, project_name=None):
        def normalize_name(name):
            return re.sub(r'[^a-z0-9]', '', name.lower())

        if 'FIG_PROJECT_NAME' in os.environ:
            log.warn('The FIG_PROJECT_NAME environment variable is deprecated.')
            log.warn('Please use COMPOSE_PROJECT_NAME instead.')

        project_name = project_name or os.environ.get('COMPOSE_PROJECT_NAME') or os.environ.get('FIG_PROJECT_NAME')
        if project_name is not None:
            return normalize_name(project_name)

        project = os.path.basename(os.path.dirname(os.path.abspath(config_path)))
        if project:
            return normalize_name(project)

        return 'default'

    def get_config_path(self, file_path=None):
        if file_path:
            return os.path.join(self.base_dir, file_path)

        if os.path.exists(os.path.join(self.base_dir, 'docker-compose.yaml')):
            log.warning("Compose just read the file 'docker-compose.yaml' on startup, rather "
                        "than 'docker-compose.yml'")
            log.warning("Please be aware that .yml is the expected extension "
                        "in most cases, and using .yaml can cause compatibility "
                        "issues in future")

            return os.path.join(self.base_dir, 'docker-compose.yaml')

        return os.path.join(self.base_dir, 'docker-compose.yml')
