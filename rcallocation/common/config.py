#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import dataclasses
import operator
import os
import socket
import sys

from keystoneauth1 import loading as ks_loading
from keystonemiddleware import auth_token
from oslo_config import cfg
from oslo_log import log as logging
import yaml


LOG = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = "/etc/rcallocation/rcallocation.conf"
CONFIG_FILE_ENV = "RCALLOCATION_CONFIG_FILE"
SERVICE_TYPE = "allocations"

default_opts = [
    cfg.StrOpt(
        "auth_strategy",
        default="keystone",
        choices=["noauth", "keystone", "testing"],
        help="The auth strategy for API requests. 'keystone' validates "
        "X-Auth-Token with keystonemiddleware, 'noauth' trusts identity "
        "headers sent by the caller (development only) and 'testing' "
        "installs no authentication at all.",
    ),
    cfg.StrOpt("host", default=socket.gethostname()),
]

flask_opts = [
    cfg.StrOpt("secret_key", secret=True),
    cfg.StrOpt("host", default="0.0.0.0"),
    cfg.IntOpt("port", default=5000),
]

api_opts = [
    cfg.StrOpt(
        "version",
        default="1.3",
        help="Version string reported by GET /v1/versions/.",
    ),
    cfg.IntOpt(
        "page_size",
        default=1000,
        min=1,
        help="Default number of results per page for list endpoints.",
    ),
    cfg.IntOpt(
        "max_page_size",
        default=1000,
        min=1,
        help="Largest page size a client may ask for with ?limit=.",
    ),
    cfg.BoolOpt(
        "enable_swagger_ui",
        default=False,
        help="Serve the Swagger UI at /v1/docs.",
    ),
]

database_opts = [
    cfg.StrOpt("connection", secret=True),
    cfg.IntOpt("connection_recycle_time", default=600),
    cfg.IntOpt("pool_size", default=5),
    cfg.IntOpt("max_overflow", default=10),
]

notification_opts = [
    cfg.StrOpt(
        "driver",
        default="taynac",
        choices=["taynac", "logging", "noop"],
        help="Driver used to send allocation notification emails.",
    ),
    cfg.ListOpt(
        "cc",
        default=[],
        help="Addresses copied on every allocation notification.",
    ),
    cfg.StrOpt(
        "dashboard_url",
        default="https://dashboard.rc.nectar.org.au",
        help="Base URL of the dashboard, used for links in emails.",
    ),
    cfg.BoolOpt(
        "enabled",
        default=True,
        help="Master switch for sending notifications.",
    ),
]

allocation_opts = [
    cfg.StrOpt(
        "for_code_series",
        default="ANZSRC_2020",
        choices=["ANZSRC_2008", "ANZSRC_2020"],
        help="Field of Research code series offered to new requests.",
    ),
    cfg.StrOpt(
        "mappings_file",
        default="/etc/rcallocation/mappings.yaml",
        help="YAML file holding the home_zones, home_storage_zones and "
        "site_members mappings.",
    ),
    cfg.StrOpt(
        "tenant_manager_role",
        default="tenantmanager",
        help="Keystone role whose holders on a project are treated as "
        "owners of that project's allocation.",
    ),
    cfg.IntOpt(
        "role_assignment_cache_seconds",
        default=300,
        help="How long a user's tenantmanager project list is cached.",
    ),
]

sentry_opts = [
    cfg.StrOpt(
        "dsn",
        secret=True,
        help="Sentry/GlitchTip DSN to report errors to. Error reporting "
        "is disabled if not set.",
    ),
    cfg.StrOpt(
        "environment",
        help="Environment name to tag reported errors with "
        "(e.g. production, testing).",
    ),
]

cfg.CONF.register_opts(sentry_opts, group="sentry")
cfg.CONF.register_opts(allocation_opts, group="allocations")
cfg.CONF.register_opts(notification_opts, group="notifications")
cfg.CONF.register_opts(database_opts, group="database")
cfg.CONF.register_opts(api_opts, group="api")
cfg.CONF.register_opts(flask_opts, group="flask")
cfg.CONF.register_opts(default_opts)

logging.register_options(cfg.CONF)

ks_loading.register_auth_conf_options(cfg.CONF, "service_auth")
ks_loading.register_session_conf_options(cfg.CONF, "service_auth")

for _group, _opts in auth_token.list_opts():
    cfg.CONF.register_opts(_opts, group=_group)


def set_defaults():
    """Apply the service's own defaults for library options.

    Anonymous read access relies on keystonemiddleware deferring the auth
    decision to the application, and application credential access rules
    are matched against this service's catalog type.
    """
    cfg.CONF.set_default(
        "delay_auth_decision", True, group="keystone_authtoken"
    )
    cfg.CONF.set_default(
        "service_type", SERVICE_TYPE, group="keystone_authtoken"
    )


set_defaults()


def init(args=[], conf_file=None):
    if conf_file is None:
        conf_file = os.environ.get(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE)
    default_config_files = [conf_file]
    if not os.path.exists(conf_file):
        LOG.warning("Config file %s not found, using defaults", conf_file)
        default_config_files = []
    cfg.CONF(
        args,
        project="rcallocation",
        default_config_files=default_config_files,
    )
    # cfg.CONF.reset() (used by the tests) drops set_default() values,
    # so reapply them on every init.
    set_defaults()
    reset_mappings()


def setup_logging(conf):
    """Sets up the logging options for a log with supplied name.

    :param conf: a cfg.ConfOpts object
    """
    product_name = "rcallocation"

    logging.setup(conf, product_name)
    LOG.info("Logging enabled!")
    LOG.debug("command line: %s", " ".join(sys.argv))


# Used by oslo-config-generator entry point
# https://docs.openstack.org/oslo.config/latest/cli/generator.html
def list_opts():
    return [
        ("DEFAULT", default_opts),
        ("api", api_opts),
        ("allocations", allocation_opts),
        ("database", database_opts),
        ("flask", flask_opts),
        ("notifications", notification_opts),
        ("sentry", sentry_opts),
        add_auth_opts(),
    ]


def add_auth_opts():
    opts = ks_loading.register_session_conf_options(cfg.CONF, "service_auth")
    opt_list = copy.deepcopy(opts)
    opt_list.insert(0, ks_loading.get_auth_common_conf_options()[0])
    for plugin_option in ks_loading.get_auth_plugin_conf_options("password"):
        if all(option.name != plugin_option.name for option in opt_list):
            opt_list.append(plugin_option)
    opt_list.sort(key=operator.attrgetter("name"))
    return ("service_auth", opt_list)


@dataclasses.dataclass(frozen=True)
class Mappings:
    """Site and zone mappings loaded from the mappings YAML file.

    ``home_zones`` maps a compute allocation home to its zones,
    ``home_storage_zones`` maps an allocation home to the storage zones
    considered local to it and ``site_members`` maps an email domain to
    the sites its users belong to.
    """

    home_zones: dict
    home_storage_zones: dict
    site_members: dict


_MAPPINGS = None
_MAPPING_KEYS = ("home_zones", "home_storage_zones", "site_members")


class MappingsError(Exception):
    pass


def _validate_mapping(name, mapping):
    if mapping is None:
        return {}
    if not isinstance(mapping, dict):
        raise MappingsError(f"{name} must be a mapping of name to list")
    result = {}
    for key, values in mapping.items():
        if not isinstance(key, str):
            raise MappingsError(f"{name} key {key!r} is not a string")
        if values is None:
            values = []
        if not isinstance(values, list) or not all(
            isinstance(v, str) for v in values
        ):
            raise MappingsError(
                f"{name}[{key}] must be a list of strings, got {values!r}"
            )
        result[key] = list(values)
    return result


def load_mappings(path):
    if not os.path.exists(path):
        LOG.warning("Mappings file %s not found, using empty mappings", path)
        data = {}
    else:
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise MappingsError(f"{path} must contain a mapping at the top level")
    unknown = set(data) - set(_MAPPING_KEYS)
    if unknown:
        raise MappingsError(f"{path} has unknown keys {sorted(unknown)}")
    return Mappings(
        **{key: _validate_mapping(key, data.get(key)) for key in _MAPPING_KEYS}
    )


def get_mappings():
    global _MAPPINGS
    if _MAPPINGS is None:
        _MAPPINGS = load_mappings(cfg.CONF.allocations.mappings_file)
    return _MAPPINGS


def reset_mappings():
    global _MAPPINGS
    _MAPPINGS = None
