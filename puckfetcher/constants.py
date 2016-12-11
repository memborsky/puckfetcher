"""Constants used for the puckfetcher application."""
import pkg_resources

from appdirs import AppDirs

APPDIRS = AppDirs("puckfetcher")

URL = "https://github.com/andrewmichaud/puckfetcher"

VERSION = pkg_resources.require(__package__)[0].version

USER_AGENT = __package__ + "/" + VERSION + " +" + URL

VERBOSITY = 0

ENCODING = "UTF-8"
