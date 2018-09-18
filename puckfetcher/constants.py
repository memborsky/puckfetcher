"""Constants used for the puckfetcher application."""
import appdirs
import pkg_resources

APPDIRS = appdirs.AppDirs("puckfetcher")

URL = "https://github.com/alixnovosi/puckfetcher"

VERSION = pkg_resources.require(__package__)[0].version

USER_AGENT = f"{__package__}/{VERSION} +{URL}"

VERBOSITY = 0

ENCODING = "UTF-8"
