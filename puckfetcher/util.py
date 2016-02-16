import logging
import os
import platform
import textwrap
import time

LAST_CALLED = {}

logger = logging.getLogger("root")

SYSTEM = platform.system()
HOME = os.environ.get("HOME")


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

            ret = func(*args, **kargs)
            LAST_CALLED[key] = now
            logger.debug("Updating rate limiter last called for {0} to {1}.".format(key, now))
            return ret

        return rate_limited_function
    return decorate


def get_xdg_config_home_path():
    """Provide path of XDG_CONFIG_HOME for platform, using current env value if present."""
    if SYSTEM == "Darwin":
        default = os.path.join(HOME, "Library", "Preferences")

    # TODO This doesn't handle Windows correctly, and may not handle *BSD correctly, if we care
    # about that.
    else:
        default = os.path.join(HOME, ".config")

    directory = os.getenv("XDG_CONFIG_HOME", default)
    logger.debug("Providing {0} as $XDG_CONFIG_HOME value.".format(directory))
    return get_directory_generic(directory)


def get_xdg_config_file_path(*args):
    """Provide full path to a file in XDG_CONFIG_HOME, joining args to XDG_CONFIG_HOME."""
    xdg_config_home = get_xdg_config_home_path()
    return get_file_generic(xdg_config_home, *args)


def get_xdg_config_dir_path(*args):
    """Provide full directory path in XDG_CONFIG_HOME, joining args to XDG_CONFIG_HOME."""
    xdg_config_home = get_xdg_config_home_path()
    return get_directory_generic(xdg_config_home, *args)


def get_xdg_data_home_path():
    """Provide path of XDG_DATA_HOME for platform, using current env value if present."""
    if SYSTEM == "Darwin":
        default = os.path.join(HOME, "Library")

    else:
        default = os.path.join(HOME, ".local", "share")

    directory = os.getenv("XDG_DATA_HOME", default)
    logger.debug("Providing {0} as $XDG_DATA_HOME value.".format(directory))
    return get_directory_generic(directory)


def get_xdg_data_file_path(*args):
    """Provide full path to a file in XDG_DATA_HOME, joining args to XDG_DATA_HOME."""
    xdg_data_home = get_xdg_data_home_path()
    return get_file_generic(xdg_data_home, *args)


def get_xdg_data_dir_path(*args):
    """Provide full directory path in XDG_DATA_HOME, joining args to XDG_DATA_HOME."""
    xdg_data_home = get_xdg_data_home_path()
    return get_directory_generic(xdg_data_home, *args)


def get_xdg_cache_home_path():
    """Provide path of XDG_CACHE_HOME for platform, using current env value if present."""
    if SYSTEM == "Darwin":
        default = os.path.join(HOME, "Library", "Caches")
    else:
        default = os.path.join(HOME, ".cache")

    directory = os.getenv("XDG_CACHE_HOME", default)
    logger.debug("Providing {0} as $XDG_CACHE_HOME value.".format(directory))
    return get_directory_generic(directory)


def get_xdg_cache_file_path(*args):
    """Provide full path to a file in XDG_CACHE_HOME, joining args to XDG_CACHE_HOME."""
    xdg_cache_home = get_xdg_cache_home_path()
    return get_file_generic(xdg_cache_home, *args)


def get_xdg_cache_dir_path(*args):
    """Provide full directory path in XDG_CACHE_HOME, joining args to XDG_CACHE_HOME."""
    xdg_cache_home = get_xdg_cache_home_path()
    return get_directory_generic(xdg_cache_home, *args)


def get_file_generic(*args):
    """Get full file path from args, creating intermediate directories and file if needed."""
    full_path = os.path.join(*args)

    directory, _ = os.path.split(full_path)

    get_directory_generic(directory)

    if not os.path.exists(full_path):
        logger.debug("Creating file {0}.".format(full_path))
        open(full_path, "a").close()

    return full_path


def get_directory_generic(*args):
    """Get full directory path from args, creating intermediate and final directories if needed."""
    full_path = os.path.join(*args)

    if not os.path.exists(full_path):
        logger.debug("Creating directories in path {0}.".format(full_path))
        os.makedirs(full_path)

    return full_path
