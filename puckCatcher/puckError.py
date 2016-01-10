class PuckError(Exception):
    """
    Generic Exception for errors in this project.
    """
    pass


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
