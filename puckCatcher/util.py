import time

LAST_CALLED = {}


# Modified from https://stackoverflow.com/a/667706
def RateLimited(maxPerHour):
    """Decorator to limit function to N calls/hour."""
    minInterval = 3600.0 / float(maxPerHour)

    def decorate(func):
        if func.__name__ not in LAST_CALLED:
            LAST_CALLED[func.__name__] = 0.0

        def rateLimitedFunction(*args, **kargs):
            lastCalled = LAST_CALLED[func.__name__]
            elapsed = time.time() - lastCalled
            remaining = minInterval - elapsed
            if remaining > 0:
                print("Self-enforced rate limit hit, sleeping {0} seconds.".format(remaining))
                time.sleep(remaining)

            ret = func(*args, **kargs)
            LAST_CALLED[func.__name__] = time.time()
            return ret

        return rateLimitedFunction

    return decorate
