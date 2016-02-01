import os
import platform
import time

LAST_CALLED = {}


# Modified from https://stackoverflow.com/a/667706
def rate_limited(max_per_hour, *args):
    """Decorator to limit function to N calls/hour."""
    min_interval = 3600.0 / float(max_per_hour)

    def decorate(func):
        things = [func.__name__]
        things.extend(args)
        key = "".join(things)
        if key not in LAST_CALLED:
            LAST_CALLED[key] = 0.0

        def rate_limited_function(*args, **kargs):
            last_called = LAST_CALLED[key]
            now = time.time()
            elapsed = now - last_called
            remaining = min_interval - elapsed
            print("last_called", last_called)
            print("remaining", remaining)
            if remaining > 0 and last_called > 0.0:
                print("Self-enforced rate limit hit, sleeping {0} seconds.".format(remaining))
                time.sleep(remaining)

            ret = func(*args, **kargs)
            LAST_CALLED[key] = now
            return ret

        return rate_limited_function

    return decorate


# NOTE I don't know if it's XDG spec to dump into Library on OSX, but most applications there do
# that, so I'm going to stick with it.
def get_xdg_config_dir_path(*args):
    """Return XDG Base Spec Config dir, taking into account platform. Append arguments to path."""
    system = platform.system()
    if system == "Darwin":
        default_config = os.path.join(os.environ.get("HOME"), "Library", "Preferences")

    # TODO This doesn't handle Windows correctly, and may not handle *BSD correctly, if we care
    # about that.
    else:
        default_config = os.path.join(os.environ.get("HOME"), ".config")

    return os.path.join(os.getenv("XDG_CONFIG_HOME", default_config), *args)


def get_xdg_data_dir_path(*args):
    """Return XDG Base Spec Data dir, taking into account platform. Append arguments to path."""
    system = platform.system()
    if system == "Darwin":
        default_data = os.path.join(os.environ.get("HOME"), "Library")

    else:
        default_data = os.path.join(os.environ.get("HOME"), ".local", "share")

    return os.path.join(os.getenv("XDG_DATA_HOME", default_data), *args)


def get_xdg_cache_dir_path(*args):
    """Return XDG Base Spec Cache dir, taking into account platform. Append arguments to path."""
    system = platform.system()
    if system == "Darwin":
        default_cache = os.path.join(os.environ.get("HOME"), "Library", "Caches")

    else:
        default_cache = os.path.join(os.environ.get("HOME"), ".cache")

    return os.path.join(os.getenv("XDG_CACHE_HOME", default_cache), *args)
