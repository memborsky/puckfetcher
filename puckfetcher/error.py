"""Errors for puckfetcher."""

class PuckError(Exception):
    """
    Generic Exception for errors in this project.

    Attributes:
        desc    -- short message describing error
    """
    def __init__(self, desc):
        super(PuckError, self).__init__()
        self.desc = desc

class BadCommandError(PuckError):
    """
    Exception raised when a command is given bad arguments.
    Attributes:
        desc -- short message describing error.
    """
    def __init__(self, desc):
        super(BadCommandError, self).__init__(desc)

class MalformedConfigError(PuckError):
    """
    Exception raised when we were provided invalid options during Config construction.

    Attributes:
        desc    -- short message describing error
    """
    def __init__(self, desc):
        super(MalformedConfigError, self).__init__(desc)

class MalformedSubscriptionError(PuckError):
    """
    Exception raised when we were provided invalid options during Subscription construction.

    Attributes:
        desc -- short message describing error
    """
    def __init__(self, desc):
        super(MalformedSubscriptionError, self).__init__(desc)
