"""Utility methods for Python packages (written with puckfetcher in mind)."""

import logging
import os
import time
try:
    from urlparse import urlparse
except ImportError:
    # pylint: disable=no-name-in-module, import-error
    from urllib.parse import urlparse

import requests
from clint.textui import progress

LOG = logging.getLogger("root")

LAST_CALLED = {}

# I'm unsure if this the best way to do this.
# TODO don't support andrewmichaud.com, we should have proper local file support eventually, and
# run tests with that.
RATELIMIT_DOMAIN_WHITELIST = ["andrewmichaud.com"]


def generate_downloader(headers, args):
    """Create function to download with rate limiting and text progress."""

    def _downloader(url, dest, overwrite=True):
        # If there is a file with the name we intend to save to, assume the podcast has
        # been downloaded already.
        if os.path.isfile(dest) and not overwrite:
            LOG.info("File %s exists, not overwriting, assuming downloaded.", dest)
            print("File exists. Assuming already downloaded and skipping.")
            return

        domain = urlparse(url).netloc
        if domain == "":
            domain = "localhost"

        @rate_limited(domain, 30, args)
        def _rate_limited_download():
            response = requests.get(url, headers=headers, stream=True)
            LOG.info("Actually downloading from %s", url)
            LOG.info("Trying to save to %s", dest)

            total_length = int(response.headers.get("content-length"))
            expected_size = (total_length / 1024) + 1
            chunks = response.iter_content(chunk_size=1024)

            open(dest, "a").close()
            # per http://stackoverflow.com/a/20943461
            with open(dest, "wb") as stream:
                for chunk in progress.bar(chunks, expected_size=expected_size):
                    if not chunk:
                        return
                    stream.write(chunk)
                    stream.flush()

        _rate_limited_download()

    return _downloader


def max_clamp(val, cap):
    """Clamp int to maximum."""
    return min(val, cap)


def expand(directory):
    """Apply expanduser and expandvars to directory to expand '~' and env vars."""
    temp1 = os.path.expanduser(directory)
    return os.path.expandvars(temp1)


def sanitize(filename):
    """
    Remove disallowed characters from potential filename. Currently only guaranteed on Linux and
    OS X.
    """
    return filename.replace("/", "-")


def parse_int_string(int_string):
    """
    Given a string like "1 23 4-8 32 1", return a unique list of those integers in the string and
    the integers in the ranges in the string.
    Non-numbers ignored.
    """
    cleaned_spaces = " ".join(int_string.strip().split())
    cleaned_dashes = cleaned_spaces.replace(" - ", "-")

    tokens = cleaned_dashes.split(" ")
    indices = set()
    for token in tokens:
        if "-" in token:
            endpoints = token.split("-")
            if len(endpoints) != 2:
                LOG.info("Dropping token %s as invalid - weird range.", token)
                continue

            start = int(endpoints[0])
            end = int(endpoints[1]) + 1

            indices = indices.union(indices, set(range(start,end)))

        else:
            try:
                indices.add(int(token))
            except ValueError:
                LOG.info("Dropping token %s as invalid - not an int.", token)

    return list(indices)


# Modified from https://stackoverflow.com/a/667706
def rate_limited(domain, max_per_hour, *args):
    """Decorator to limit function to N calls/hour."""
    min_interval = 3600.0 / float(max_per_hour)

    def _decorate(func):
        things = [func.__name__]
        things.extend(args)
        key = "".join(things)
        LOG.debug("Rate limiter called for %s.", key)
        if key not in LAST_CALLED:
            LOG.debug("Initializing entry for %s.", key)
            LAST_CALLED[key] = 0.0

        def _rate_limited_function(*args, **kargs):
            last_called = LAST_CALLED[key]
            now = time.time()
            elapsed = now - last_called
            remaining = min_interval - elapsed
            LOG.debug("Rate limiter last called for '%s' at %s.", key, last_called)
            LOG.debug("Remaining cooldown time for '%s' is %s.", key, remaining)

            if not skip_rate_limiting(domain) and remaining > 0 and last_called > 0.0:
                LOG.info("Self-enforced rate limit hit, sleeping %s seconds.", remaining)
                time.sleep(remaining)

            LAST_CALLED[key] = time.time()
            ret = func(*args, **kargs)
            LOG.debug("Updating rate limiter last called for %s to %s.", key, now)
            return ret

        return _rate_limited_function
    return _decorate

def skip_rate_limiting(domain):
    """Provide a hack to skip rate limiting during tests, for certain domains."""
    res = False
    for sub_url in RATELIMIT_DOMAIN_WHITELIST:
        if sub_url in domain:
            res = True
            break

    return res
