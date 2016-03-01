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


# TODO this needs reworking to split out of one class without losing the setup/teardown
class TestSubscription:
    @classmethod
    def setup_class(cls):
        cls.xdg_config_home = tempfile.mkdtemp()
        cls.old_xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
        os.environ["XDG_CONFIG_HOME"] = cls.xdg_config_home

        cls.xdg_cache_home = tempfile.mkdtemp()
        cls.old_xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "")
        os.environ["XDG_CACHE_HOME"] = cls.xdg_cache_home

        cls.xdg_data_home = tempfile.mkdtemp()
        cls.old_xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
        os.environ["XDG_DATA_HOME"] = cls.xdg_data_home

        cls.d = os.path.join(cls.xdg_data_home, "tmp")

    @classmethod
    def teardown_class(cls):
        os.environ["XDG_CONFIG_HOME"] = cls.old_xdg_config_home
        os.environ["XDG_CACHE_HOME"] = cls.old_xdg_cache_home
        os.environ["XDG_DATA_HOME"] = cls.old_xdg_data_home

        shutil.rmtree(cls.xdg_config_home)
        shutil.rmtree(cls.xdg_cache_home)
        shutil.rmtree(cls.xdg_data_home)

    def test_empty_url_construction_errors(self):
        """
        Constructing a subscription with a URL that is empty should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(url="", name="emptyConstruction", directory=TestSubscription.d)

        assert(e.value.desc == "No URL provided.")

    def test_none_url_construction_errors(self):
        """
        Constructing a subscription with a URL that is None should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(name="noneConstruction", directory=TestSubscription.d)

        assert(e.value.desc == "No URL provided.")

    def test_empty_name_construction_errors(self):
        """
        Constructing a subscription with a name that is empty should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(url="foo", name="", directory=TestSubscription.d)

        assert(e.value.desc == "No name provided.")

    def test_none_name_construction_errors(self):
        """
        Constructing a subscription with a name that is None should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(url="foo", name=None, directory=TestSubscription.d)

        assert(e.value.desc == "No name provided.")

    def test_get_feed_helper_fails_after_max(self):
        """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
        sub = SUB.Subscription(url=http302Address, name="tooManyAttemptsTest",
                               directory=TestSubscription.d)

        # TODO tests need to be rewritten to check log output or something.
        sub._get_feed_helper(attempt_count=SUB.MAX_RECURSIVE_ATTEMPTS+1)

        assert(sub.feed is None)
        assert(sub.entries is None)

    def test_valid_temporary_redirect_succeeds(self):
        """
        If we are redirected temporarily to a valid RSS feed, we should successfully parse that
        feed and not change our url. The originally provided URL should be unchanged.
        """

        sub = SUB.Subscription(url=http302Address, name="302Test", directory=TestSubscription.d)
        sub.get_feed()

        assert(sub.entries[0]["link"] == rssResourceAddress)
        assert(sub._current_url == http302Address)
        assert(sub._provided_url == http302Address)

    def test_valid_permanent_redirect_succeeds(self):
        """
        If we are redirected permanently to a valid RSS feed, we should successfully parse that
        feed and change our url.  The originally provided URL should be unchanged
        """

        sub = SUB.Subscription(url=http301Address, name="301Test", directory=TestSubscription.d)
        sub.get_feed()

        assert(sub.entries[0]["link"] == rssResourceAddress)
        assert(sub._current_url == rssAddress)
        assert(sub._provided_url == http301Address)

    def test_not_found_fails(self):
        """If the URL is Not Found, we should not change the saved URL."""

        sub = SUB.Subscription(url=http404Address, name="404Test", directory=TestSubscription.d)
        sub.get_feed()

        assert(sub._current_url == http404Address)
        assert(sub._provided_url == http404Address)

    def test_gone_fails(self):
        """If the URL is Gone, the current url should be set to None, and we should return None."""

        sub = SUB.Subscription(url=http410Address, name="410Test", production=False,
                               directory=TestSubscription.d)
        sub.get_feed()

        assert(sub._current_url is None)
        assert(sub._provided_url == http410Address)

    # TODO attempt to make tests that are less fragile/dependent on my website configuration/files.
    def test_attempt_download_backlog(self):
        """Should download full backlog by default."""
        sub = SUB.Subscription(url=rssAddress, name="testfeed", production=False,
                               directory=TestSubscription.d)
        sub.attempt_update()

        assert(len(sub.entries) == 10)
        for i in range(1, 9):
            f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
            with open(f, "r") as enclosure:
                data = enclosure.read().replace('\n', '')
                assert(data == "hi")

    def test_attempt_download_partial_backlog(self):
        """Should download partial backlog if limit is specified."""
        sub = SUB.Subscription(url=rssAddress, name="testfeed", backlog_limit=5, production=False,
                               directory=TestSubscription.d)
        sub.attempt_update()

        assert(len(sub.entries) == 10)
        for i in range(5, 9):
            f = os.path.join(sub.directory, "hi0{0}.txt".format(i))
            with open(f, "r") as enclosure:
                data = enclosure.read().replace('\n', '')
                assert(data == "hi")
