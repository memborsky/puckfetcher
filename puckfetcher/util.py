import logging
import os
import platform
import textwrap
import time

logger = logging.getLogger("root")

HOME = os.environ.get("HOME")
LAST_CALLED = {}
SYSTEM = platform.system()
APPNAME = "puckfetcher"

if SYSTEM == "Darwin":
    CACHE_DIR = os.path.join(HOME, "Library", "Caches")
    CONFIG_DIR = os.path.join(HOME, "Library", "Preferences")
    DATA_DIR = os.path.join(HOME, "Library")

# TODO This doesn't handle Windows correctly, and may not handle *BSD correctly, if we care about
# that.
else:
    CACHE_DIR = os.path.join(HOME, ".cache")
    CONFIG_DIR = os.path.join(HOME, ".config")
    DATA_DIR = os.path.join(HOME, ".local", "share")

CACHE_DIR = os.environ.get("XDG_CACHE_HOME", CACHE_DIR)
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", CONFIG_DIR)
DATA_DIR = os.environ.get("XDG_DATA_HOME", DATA_DIR)

for d in [CACHE_DIR, CONFIG_DIR, DATA_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)


# Modified from https://stackoverflow.com/a/667706
def rate_limited(production, max_per_hour, *args):
    """Decorator to limit function to N calls/hour."""
    min_interval = 3600.0 / float(max_per_hour)

    def decorate(func):
        things = [func.__name__]
        things.extend(args)
        key = "".join(things)
        logger.debug("Rate limiter called for {0}.".format(key))
        if key not in LAST_CALLED:
            logger.debug("Initializing entry for {0}.".format(key))
            LAST_CALLED[key] = 0.0

        def rate_limited_function(*args, **kargs):
            last_called = LAST_CALLED[key]
            now = time.time()
            elapsed = now - last_called
            remaining = min_interval - elapsed
            logger.debug("Rate limiter last called for '{0}' at {1}.".format(key, last_called))
            logger.debug("Remaining cooldown time for '{0}' is {1}.".format(key, remaining))

            if production and remaining > 0 and last_called > 0.0:
                logger.info(textwrap.dedent(
                    "Self-enforced rate limit hit, sleeping {0} seconds.".format(remaining)))
                time.sleep(remaining)

            LAST_CALLED[key] = time.time()
            ret = func(*args, **kargs)
            logger.debug("Updating rate limiter last called for {0} to {1}.".format(key, now))
            return ret

        return rate_limited_function
    return decorate


def get_config_path(filename=""):
    """Get path to config directory or file, optionally a file in that directory."""
    return os.path.join(CONFIG_DIR, filename)


def get_cache_path(filename=""):
    """Get path to cache directory or file, optionally a file in that directory."""
    return os.path.join(CACHE_DIR, filename)


def get_data_path(filename=""):
    """Get path to data directory, optionally a file in that directory."""
    return os.path.join(DATA_DIR, filename)
