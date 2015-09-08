"""
Copyright (c) 2012-2014 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

# for CentOS nut systemd files are:-
# from nut package
# /usr/lib/systemd/system/nut-driver.service
# /usr/lib/systemd/system/nut-server.service
# N.B. the Type=simple so just a process start
# the nut-server requires the nut-driver and is started before:-
# from nut-client package
# /usr/lib/systemd/system/nut-monitor.service
# /lib/systemd/system-shutdown/nutshutdown
# note nut-monitor.service is set to start after nut-server.service

# N.B. some config options passed to nut from service configuration are used
# in multiple configuration files ie upsname in ups.conf and upsmon.conf

import re
import collections
from tempfile import mkstemp
from shutil import move
import logging

logger = logging.getLogger(__name__)

# CONSTANTS of file names and associated tuples (immutable lists) of accepted
# / known options in those config files
# in a more abstract sense these might be better as collections.namedtuples
NUT_CONFIG = '/etc/ups/nut.conf'
NUT_CONFIG_OPTIONS = ("MODE")
NUT_UPS_CONFIG = '/etc/ups/ups.conf'
NUT_UPS_CONFIG_OPTIONS = ("upsname", "driver", "port", "cable", "desc")
NUT_UPSD_CONFIG = '/etc/ups/upsd.conf'
NUT_UPSD_CONFIG_OPTIONS = ("LISTEN", "MAXAGE")
NUT_USERS_CONFIG = '/etc/ups/upsd.users'
NUT_USERS_CONFIG_OPTIONS = ("nutuser", "nutuserpass", "upsmon")
NUT_MONITOR_CONFIG = '/etc/ups/upsmon.conf'
NUT_MONITOR_CONFIG_OPTIONS = ("upsname", "nutserver", "nutuser", "nutuserpass")

# a dictionary for each config files associated known options.
nut_options_dict = {NUT_CONFIG: NUT_CONFIG_OPTIONS,
                    NUT_UPS_CONFIG: NUT_UPS_CONFIG_OPTIONS,
                    NUT_UPSD_CONFIG: NUT_UPSD_CONFIG_OPTIONS,
                    NUT_USERS_CONFIG: NUT_USERS_CONFIG_OPTIONS,
                    NUT_MONITOR_CONFIG: NUT_MONITOR_CONFIG_OPTIONS}

# dictionary of entries like this:- {'path-to-file', {OrderedDict-of-options}}
nut_configs = {NUT_CONFIG: collections.OrderedDict,
               NUT_UPS_CONFIG: collections.OrderedDict,
               NUT_UPSD_CONFIG: collections.OrderedDict,
               NUT_USERS_CONFIG: collections.OrderedDict,
               NUT_MONITOR_CONFIG: collections.OrderedDict}

# a dictionary to identify what options are section headers in what files
nut_section_heads = {"upsname": NUT_UPS_CONFIG, "nutuser": NUT_USERS_CONFIG}

# strings to separate auto config options from rest of config file.
RHEADER = '####BEGIN: Rockstor NUT Config####'
RHEADER2 = '####Autogenerated. Do not edit below this line####'


def configure_nut(config):
    """
    Top level nut config function.
    :param config: sanitized config from input form
    :return:
    """
    # pre process the config options so we know which files to put what options
    # in and in what order
    all_nut_configs = pre_process_nut_config(config)
    # now go through each file - options pair and apply the config
    for config_file, config_options in all_nut_configs.items():
        update_config_in(config_file, config_options)


def pre_process_nut_config(config):
    """
    Populates a dictionary of dictionaries where the top level dict is indexed
    by the a config file path & name, each config file is paired with an
    OrderedDict of options. This way we have: "file -> options_in_order" pairs.
    There is a need for OrderedDict as entries in the options per filename need
    to be able to create for example:-
    [myups]
    driver = apcsmart
    port = /dev/ttyS1
    cable = 1234
    desc = "old-apc"
    from:-
    {'/etc/ups/ups.conf' : {'upsname': 'myups', 'driver': 'apcsmart', 'port',
    '/dev/ttyS1', 'cable': '1234', 'desc': 'old-apc'} }
    Problem:- how do we know what a section header is?
    Answer is the specific pre_processors know this so can change
    for example 'upsname': 'myups' pair to 'section--upsname': 'myups' and only
    gain information as the key value is a section not a something= entry
    then we can act accordingly (see update_config_in for implementation)

    :param config: sanitized config dict from form entry
    :return: dict of OrderedDict's of 'file': {key: value}
    """

    # move section headings from config to nut_configs OrderedDicts
    # this way all following entries will pertain to them in their respective
    # config files. Assumes each section head is required in at most one file
    for section_header, config_file in nut_section_heads.items():
        if section_header in config:
            # we have found a config item that should be a section header so
            # pop it out from config and add it to the appropriate nut_configs
            nut_configs[config_file][section_header] = config.pop(
                section_header)

    # iterate over the nut_options_dict to allocate the configs to the
    # right section in nut_configs so they can applied to the correct file.
    # N.B. we don't pop from config as some options are used in multiple files
    for config_file, file_options in nut_options_dict.items():
        # now repeatedly match config's entries to our host loops offerings.
        for config_option, config_value in config.items():
            if config_option in file_options:
                # add this config_option and value pair to our nut_configs
                nut_configs[config_file][config_option] = config_value


def update_config_in(file, config):
    """
    # potentially upgrade this to a generic config writer via class def
    Remark out all occurrences of
    options in dict-of-options above HEADER and paste them in after HEADER.
    Create the HEADER if not found.
    Also deal with config file sections and subsections.
    :param file: path and filename of config file to update
    :param config: OrderedDict of options
    :return:
    """

    # now write out our config including section headers which should come
    # before their subsection counterparts courtesy of pre-processing.
    for option, value in config.items():
        if re.match("section--", option) is not None:
            # to cheaply regain the section header from this key we can:-
            # index.replace('section--', '')
            section_head = '[' + value + ']'
