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

# pylint: disable=invalid-name
logger = logging.getLogger("root")

LAST_CALLED = {}

# I'm unsure if this the best way to do this.
# TODO don't support andrewmichaud.com, we should have proper local file support eventually, and
# run tests with that.
RATELIMIT_DOMAIN_WHITELIST = ["localhost", "www.andrewmichaud.com"]


def generate_downloader(headers, args):
    """Create function to download with rate limiting and text progress."""

    def _downloader(url, dest, overwrite=True):
        # If there is a file with the name we intend to save to, assume the podcast has
        # been downloaded already.
        if os.path.isfile(dest) and not overwrite:
            logger.info("File %s exists, not overwriting, assuming downloaded.", dest)
            return

        domain = urlparse(url).netloc
        if domain == "":
            domain = "localhost"

        @rate_limited(domain, 30, args)
        def _rate_limited_download():
            response = requests.get(url, headers=headers, stream=True)
            logger.info("Actually downloading from %s", url)

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


def max_clamp(val, m):
    """Clamp int to maximum."""
    return min(val, m)


# Modified from https://stackoverflow.com/a/667706
def rate_limited(domain, max_per_hour, *args):
    """Decorator to limit function to N calls/hour."""
    min_interval = 3600.0 / float(max_per_hour)

    def _decorate(func):
        things = [func.__name__]
        things.extend(args)
        key = "".join(things)
        logger.debug("Rate limiter called for %s.", key)
        if key not in LAST_CALLED:
            logger.debug("Initializing entry for %s.", key)
            LAST_CALLED[key] = 0.0

        def _rate_limited_function(*args, **kargs):
            last_called = LAST_CALLED[key]
            now = time.time()
            elapsed = now - last_called
            remaining = min_interval - elapsed
            logger.debug("Rate limiter last called for '%s' at %s.", key, last_called)
            logger.debug("Remaining cooldown time for '%s' is %s.", key, remaining)

            if domain not in RATELIMIT_DOMAIN_WHITELIST and remaining > 0 and last_called > 0.0:
                logger.info("Self-enforced rate limit hit, sleeping %s seconds.", remaining)
                time.sleep(remaining)

            LAST_CALLED[key] = time.time()
            ret = func(*args, **kargs)
            logger.debug("Updating rate limiter last called for %s to %s.", key, now)
            return ret

        return _rate_limited_function
    return _decorate
