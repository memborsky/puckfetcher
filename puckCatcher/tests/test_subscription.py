import nose
from nose.tools import *

import puckCatcher.subscription as SUB
import puckCatcher.puckError as PE

rssTestHost = "https://www.andrewmichaud.com/"
rssAddress = rssTestHost + "rss.xml"
rssResourceAddress = rssTestHost + "hi.txt"
http302Address = rssTestHost + "302rss.xml"
http301Address = rssTestHost + "301rss.xml"
http404Address = rssTestHost + "404rss.xml"
http410Address = rssTestHost + "410rss.xml"

@raises(PE.MalformedFeedError)
def test_emptyUrlConstructionErrors():
    """An empty URL should throw a MalformedFeedError"""
    sub = SUB.Subscription(url="", name="emptyConstruction")

@raises(PE.MalformedFeedError)
def test_noneUrlConstructionErrors():
    """An None URL should throw a MalformedFeedError"""
    sub = SUB.Subscription(name="noneConstruction")

def test_emptyDaysConstructedCorrectly():
    """
    A subscription constructed with an empty days list should have an array
    of all false for its days list.
    """
    emptySubscription = SUB.Subscription(url=rssAddress)
    assert(emptySubscription.days == [False]*7)

def test_numberDaysConstructedCorrectly():
    """
    A subscription initialized with day numbers should parse them correctly.
    Invalid days should be silently ignored.
    """
    sub = SUB.Subscription(name="numberDaysTest", url=rssAddress, days=[1, 2, 42, 5, 7, 0, 0, 1, 2])
    assert(sub.days == [True, True, False, False, True, False, True])

def test_stringDaysConstructedCorrectly():
    """
    A subscription initialized with day strings should parse them correctly.
    Invalid strings should be silently ignored.
    """
    sub = SUB.Subscription(name="stringDaysTest",
                           url=rssAddress,
                           days=[ "Monday"
                                , "Tuesday"
                                , "Wed"
                                , "Fish"
                                , "Friiiiiiiiiiiday"
                                , "Sunblargl"])
    assert(sub.days == [True, True, True, False, True, False, True])

def test_mixedDaysParsedCorrectly():
    """
    A mixture of string and int days should be parsed correctly.
    Invalid elements should be silently ignored.
    """
    sub = SUB.Subscription(name="mixedDaysTest",
                           url=rssAddress,
                           days=[ "Monday"
                                , 2
                                , "Wed"
                                , "Fish"
                                , 42
                                , "Friiiiiiiiiiiday"
                                , "Sunblargl"])
    assert(sub.days == [True, True, True, False, True, False, True])


def test_emptyURLAfterConstructionFails():
    """If we set the URL to empty after construction, getting latest entry should fail."""
    sub = SUB.Subscription(url=http302Address, name="emptyTest")
    sub.currentUrl = ""
    assert(sub.getLatestEntry() is None);


def test_noneURLAfterConstructionFails():
    """If we set the URL to None after construction, getting latest entry should fail."""
    sub = SUB.Subscription(url=http302Address, name="noneTest")
    sub.currentUrl = None
    assert(sub.getLatestEntry() is None);


def test_getLatestEntryHelperFailsAfterMax():
    """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
    sub = SUB.Subscription(url=http302Address, name="tooManyAttemptsTest")
    assert(sub.getLatestEntryHelper(SUB.MAX_RECURSIVE_ATTEMPTS+1) == None)


def test_validTemporaryRedirectSucceeds():
    """
    If we are redirected temporarily to a valid RSS feed, we should successfully parse that feed
    and not change our url. The originally provided URL should be unchanged.
    """

    sub = SUB.Subscription(url=http302Address, name="302Test")
    assert(sub.getLatestEntry()["link"] == rssResourceAddress)
    assert(sub.currentUrl == http302Address)
    assert(sub.providedUrl == http302Address)


def test_validPermanentRedirectSucceeds():
    """
    If we are redirected permanently to a valid RSS feed, we should successfully parse that feed
    and change our url.  The originally provided URL should be unchanged
    """

    sub = SUB.Subscription(url=http301Address, name="301Test")
    assert(sub.getLatestEntry()["link"] == rssResourceAddress)
    assert(sub.currentUrl == rssAddress)
    assert(sub.providedUrl == http301Address)


def test_notFoundFails():
    """
    If the URL is Not Found, we should not change the saved URL, but we should return None.
    """

    sub = SUB.Subscription(url=http404Address, name="404Test")
    assert(sub.getLatestEntry() is None)
    assert(sub.currentUrl == http404Address)
    assert(sub.providedUrl == http404Address)


def test_goneFails():
    """
    If the URL is Gone, the currentUrl should be set to None, and we should return None.
    """

    sub = SUB.Subscription(url=http410Address, name="410Test")
    assert(sub.getLatestEntry() is None)
    assert(sub.currentUrl is None)
    assert(sub.providedUrl == http410Address)
