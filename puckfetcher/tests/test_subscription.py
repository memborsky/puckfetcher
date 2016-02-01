import shutil
import os

import nose.tools as NT

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
    with NT.assert_raises(PE.MalformedSubscriptionError) as e:
        SUB.Subscription(url="", name="emptyConstruction")

    NT.assert_equal(e.exception.desc, "No URL provided.")


def test_none_url_construction_errors():
    """
    Constructing a subscription with a URL that is None should throw a MalformedSubscriptionError.
    """
    with NT.assert_raises(PE.MalformedSubscriptionError) as e:
        SUB.Subscription(name="noneConstruction")

    NT.assert_equal(e.exception.desc, "No URL provided.")


def test_empty_url_after_construction_fails():
    """If we set the URL to empty after construction, getting latest entry should fail."""
    sub = SUB.Subscription(url=http302Address, name="emptyTest")
    sub.current_url = ""
    with NT.assert_raises(PE.MalformedSubscriptionError) as e:
        sub.get_feed()

    NT.assert_equal(e.exception.desc, "No URL after construction of subscription.")


def test_none_url_after_construction_fails():
    """If we set the URL to None after construction, getting latest entry should fail."""
    sub = SUB.Subscription(url=http302Address, name="noneTest")
    sub.current_url = None
    with NT.assert_raises(PE.MalformedSubscriptionError) as e:
        sub.get_feed()

    NT.assert_equal(e.exception.desc, "No URL after construction of subscription.")


def test_get_feed_helper_fails_after_max():
    """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
    sub = SUB.Subscription(url=http302Address, name="tooManyAttemptsTest")
    with NT.assert_raises(PE.UnreachableFeedError) as e:
        sub.get_feed_helper(attempt_count=SUB.MAX_RECURSIVE_ATTEMPTS+1)

    NT.assert_equal(e.exception.desc, "Too many attempts needed to reach feed.")


def test_valid_temporary_redirect_succeeds():
    """
    If we are redirected temporarily to a valid RSS feed, we should successfully parse that feed
    and not change our url. The originally provided URL should be unchanged.
    """

    sub = SUB.Subscription(url=http302Address, name="302Test")
    sub.get_feed()
    print(sub.feed)
    NT.assert_equal(sub.feed["entries"][0]["link"], rssResourceAddress)
    NT.assert_equal(sub.current_url, http302Address)
    NT.assert_equal(sub.provided_url, http302Address)


def test_valid_permanent_redirect_succeeds():
    """
    If we are redirected permanently to a valid RSS feed, we should successfully parse that feed
    and change our url.  The originally provided URL should be unchanged
    """

    sub = SUB.Subscription(url=http301Address, name="301Test")
    sub.get_feed()
    NT.assert_equal(sub.feed["entries"][0]["link"], rssResourceAddress)
    NT.assert_equal(sub.current_url, rssAddress)
    NT.assert_equal(sub.provided_url, http301Address)


def test_not_found_fails():
    """If the URL is Not Found, we should not change the saved URL, but we should return None."""

    sub = SUB.Subscription(url=http404Address, name="404Test")
    with NT.assert_raises(PE.UnreachableFeedError) as e:
        sub.get_feed()

    NT.assert_equal(sub.feed, None)
    NT.assert_equal(e.exception.desc, "Unable to retrieve feed.")
    NT.assert_equal(sub.current_url, http404Address)
    NT.assert_equal(sub.provided_url, http404Address)


def test_gone_fails():
    """If the URL is Gone, the current url should be set to None, and we should return None."""

    sub = SUB.Subscription(url=http410Address, name="410Test", production=False)
    with NT.assert_raises(PE.UnreachableFeedError) as e:
        sub.get_feed()

    NT.assert_equal(sub.feed, None)
    NT.assert_equal(e.exception.desc, "Unable to retrieve feed.")
    NT.assert_equal(sub.current_url, None)
    NT.assert_equal(sub.provided_url, http410Address)


# TODO attempt to make tests that are less fragile/dependent on my website configuration/files.
def test_attempt_download_backlog():
    """Should download full backlog by default."""
    sub = SUB.Subscription(url=rssAddress, name="testfeed", production=False)
    sub.attempt_update()

    NT.assert_equal(len(sub.feed["entries"]), 10)
    for i in range(0, 1):
        f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
        with open(f, "r") as enclosure:
            data = enclosure.read().replace('\n', '')
            NT.assert_equal(data, "hi")

    # TODO wrap this up for a workspace setup/teardown.
    shutil.rmtree(sub.directory)


def test_attempt_download_partial_backlog():
    """Should download partial backlog if limit is specified."""
    sub = SUB.Subscription(url=rssAddress, name="testfeed", backlog_limit=5, production=False)
    sub.attempt_update()

    NT.assert_equal(len(sub.feed["entries"]), 10)
    for i in range(0, 5):
        f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
        with open(f, "r") as enclosure:
            data = enclosure.read().replace('\n', '')
            NT.assert_equal(data, "hi")

    # TODO wrap this up for a workspace setup/teardown.
    shutil.rmtree(sub.directory)
