import shutil
import os
import tempfile

import pytest as PT

import puckfetcher.subscription as SUB
import puckfetcher.error as PE

rssTestHost = "https://www.andrewmichaud.com/"
rssAddress = rssTestHost + "rss.xml"
rssResourceAddress = rssTestHost + "hi.txt"
http302Address = rssTestHost + "302rss.xml"
http301Address = rssTestHost + "301rss.xml"
http404Address = rssTestHost + "404rss.xml"
http410Address = rssTestHost + "410rss.xml"

# TODO investigate spec-style tests


def test_empty_url_construction_errors():
    """
    Constructing a subscription with a URL that is empty should throw a MalformedSubscriptionError.
    """
    with PT.raises(PE.MalformedSubscriptionError) as e:
        SUB.Subscription(url="", name="emptyConstruction")

    assert(e.value.desc == "No URL provided.")


def test_none_url_construction_errors():
    """
    Constructing a subscription with a URL that is None should throw a MalformedSubscriptionError.
    """
    with PT.raises(PE.MalformedSubscriptionError) as e:
        SUB.Subscription(name="noneConstruction")

    assert(e.value.desc == "No URL provided.")


def test_get_feed_helper_fails_after_max():
    """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
    sub = SUB.Subscription(url=http302Address, name="tooManyAttemptsTest")
    with PT.raises(PE.UnreachableFeedError) as e:
        sub._get_feed_helper(attempt_count=SUB.MAX_RECURSIVE_ATTEMPTS+1)

    assert(e.value.desc == "Too many attempts needed to reach feed.")


def test_valid_temporary_redirect_succeeds():
    """
    If we are redirected temporarily to a valid RSS feed, we should successfully parse that feed
    and not change our url. The originally provided URL should be unchanged.
    """

    sub = SUB.Subscription(url=http302Address, name="302Test")
    sub.get_feed()
    assert(sub.feed["entries"][0]["link"] == rssResourceAddress)
    assert(sub._current_url == http302Address)
    assert(sub._provided_url == http302Address)


def test_valid_permanent_redirect_succeeds():
    """
    If we are redirected permanently to a valid RSS feed, we should successfully parse that feed
    and change our url.  The originally provided URL should be unchanged
    """

    sub = SUB.Subscription(url=http301Address, name="301Test")
    sub.get_feed()
    assert(sub.feed["entries"][0]["link"] == rssResourceAddress)
    assert(sub._current_url == rssAddress)
    assert(sub._provided_url == http301Address)


def test_not_found_fails():
    """If the URL is Not Found, we should not change the saved URL, but we should return None."""

    sub = SUB.Subscription(url=http404Address, name="404Test")
    with PT.raises(PE.UnreachableFeedError) as e:
        sub.get_feed()

    assert(e.value.desc == "Unable to retrieve feed.")

    assert(sub.feed is None)
    assert(sub._current_url == http404Address)
    assert(sub._provided_url == http404Address)


def test_gone_fails():
    """If the URL is Gone, the current url should be set to None, and we should return None."""

    sub = SUB.Subscription(url=http410Address, name="410Test", production=False)
    with PT.raises(PE.UnreachableFeedError) as e:
        sub.get_feed()

    assert(e.value.desc == "Unable to retrieve feed, feed is gone.")

    assert(sub.feed is None)
    assert(sub._current_url is None)
    assert(sub._provided_url == http410Address)


# TODO attempt to make tests that are less fragile/dependent on my website configuration/files.
def test_attempt_download_backlog():
    """Should download full backlog by default."""
    directory = tempfile.mkdtemp()
    sub = SUB.Subscription(url=rssAddress, name="testfeed", production=False, directory=directory)
    sub.get_feed()
    sub.attempt_update()

    assert(len(sub.feed["entries"]) == 10)
    for i in range(0, 1):
        f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
        with open(f, "r") as enclosure:
            data = enclosure.read().replace('\n', '')
            assert(data == "hi")

    # TODO wrap this up for a workspace setup/teardown.
    shutil.rmtree(sub.directory)


def test_attempt_download_partial_backlog():
    """Should download partial backlog if limit is specified."""
    directory = tempfile.mkdtemp()
    sub = SUB.Subscription(url=rssAddress, name="testfeed", backlog_limit=5, production=False,
                           directory=directory)
    sub.get_feed()
    sub.attempt_update()

    assert(len(sub.feed["entries"]) == 10)
    for i in range(5, 9):
        f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
        with open(f, "r") as enclosure:
            data = enclosure.read().replace('\n', '')
            assert(data == "hi")

    # TODO wrap this up for a workspace setup/teardown.
    shutil.rmtree(sub.directory)
