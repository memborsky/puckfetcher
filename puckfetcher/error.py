import http.client


# TODO inherit desc from this error in whatever the Python way is.
class PuckError(Exception):
    """
    Generic Exception for errors in this project.
    """
    pass


class MalformedSubscriptionError(PuckError):
    """
    Exception raised for badly formatted Subscription object.

    Attributes:
        desc -- short message describing error
    """
    def __init__(self, desc):
        self.desc = desc


class UnreachableFeedError(PuckError):
    """
    Exception raised for unreachable feeds.

    Attributes:
        desc -- short message describing error
        code -- HTTP error code, if applicable
        name -- HTTP error name, if applicable
    """
    def __init__(self, desc, code=None, name=None):
        self.desc = desc
        self.code = code
        self.name = name
        if self.name is None and self.code is not None:
            self.name = http.client.responses[self.code]


class MalformedFeedError(PuckError):
    """
    Exception raised for malformed feeds that trips feedparser's bozo alert.

    Attributes:
        desc    -- short message describing error
        bozoMsg -- bozo exception message
    """
    def __init__(self, desc, bozoMsg):
        self.desc = desc
        self.bozoMsg = bozoMsg
