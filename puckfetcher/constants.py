# -*- coding: utf-8 -*-
"""Constants used for the puckfetcher application."""
# NOTE - Python 2 shim.
from __future__ import unicode_literals

import pkg_resources

from appdirs import AppDirs

APPDIRS = AppDirs("puckfetcher")

URL = "https://github.com/andrewmichaud/puckfetcher"

VERSION = pkg_resources.require(__package__)[0].version

USER_AGENT = __package__ + "/" + VERSION + " +" + URL

VERBOSITY = 0
