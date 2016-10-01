# -*- coding: utf-8 -*-
"""Errors for puckfetcher."""
# NOTE - Python 2 shim.
from __future__ import unicode_literals

class PuckError(Exception):
    """
    Generic Exception for errors in this project.

    Attributes:
        desc    -- short message describing error
    """
    def __init__(self, desc):
        super(PuckError, self).__init__()
        self.desc = desc


class MalformedConfigError(PuckError):
    """
    Exception raised when we were provided invalid options during Config construction.

    Attributes:
        desc    -- short message describing error
    """
    def __init__(self, desc):
        super(MalformedConfigError, self).__init__(desc)

class MalformedFeedError(PuckError):
    """
    Exception raised for malformed feeds that trips feedparser's bozo alert.

    Attributes:
        desc    -- short message describing error
        bozo_msg -- bozo exception message
    """
    def __init__(self, desc, bozo_msg):
        super(MalformedFeedError, self).__init__(desc)
        self.bozo_msg = bozo_msg

class MalformedSubscriptionError(PuckError):
    """
    Exception raised when we were provided invalid options during Subscription construction.

    Attributes:
        desc -- short message describing error
    """
    def __init__(self, desc):
        super(MalformedSubscriptionError, self).__init__(desc)
