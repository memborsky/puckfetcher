"""Constants used for the puckfetcher application."""
import pkg_resources

from appdirs import AppDirs

APPDIRS = AppDirs("puckfetcher")

# TODO find a better way
# URL = pkg_resources.require(__package__)[0].url
URL = "https://github.com/andrewmichaud/puckfetcher"

VERSION = pkg_resources.require(__package__)[0].version

USER_AGENT = __package__ + "/" + VERSION + " +" + URL

VERBOSITY = 0
