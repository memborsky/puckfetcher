import http.client

class PuckError(Exception):
    """
    Generic Exception for errors in this project.
    """
    pass


class HTTPError(PuckError):
    """
    Exception raised for unrecoverable HTTP errors.

    Attributes:
        code -- HTTP error code
        name -- HTTP error name
    """
    def __init__(self, code, name=None):
        self.code = code
        self.name = name
        if self.name is None:
            self.name = http.client.responses[self.code]


class MalformedFeedError(PuckError):
    """
    Exception raised for malformed feeds that trips feedparser's bozo
    alert.

    Attributes:
        desc    -- short message describing error
        bozoMsg -- bozo exception message
    """
    def __init__(self, desc, bozoMsg):
        self.desc = desc
        self.bozoMsg = bozoMsg
