"""Tests for the subscription module."""
import shutil
import os
import tempfile

# pylint: disable=import-error
import pytest as PT

import puckfetcher.subscription as SUB
import puckfetcher.error as PE

HERE = os.path.abspath(os.path.dirname(__file__))

RSS_TEST_HOST = "https://www.andrewmichaud.com/"
# RSS_ADDRESS = os.path.join(HERE, "rss.xml")
RSS_ADDRESS = RSS_TEST_HOST + "rss.xml"
LOCAL_RESOURCE_ADDRESS = "txt/hi.txt"
REMOTE_RESOURCE_ADDRESS = "https://www.andrewmichaud.com/txt/hi.txt"
HTTP_302_ADDRESS = RSS_TEST_HOST + "302"
HTTP_301_ADDRESS = RSS_TEST_HOST + "301"
HTTP_404_ADDRESS = RSS_TEST_HOST + "404"
HTTP_410_ADDRESS = RSS_TEST_HOST + "410"


# TODO this needs reworking to split out of one class without losing the setup/teardown
class TestSubscription(object):
    """Test that a subscription has correct behavior."""
    @classmethod
    def setup_class(cls):
        """Perform stuff that should happen before all tests."""
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
        """Perform stuff that should happen after all tests."""
        os.environ["XDG_CONFIG_HOME"] = cls.old_xdg_config_home
        os.environ["XDG_CACHE_HOME"] = cls.old_xdg_cache_home
        os.environ["XDG_DATA_HOME"] = cls.old_xdg_data_home

        shutil.rmtree(cls.xdg_config_home)
        shutil.rmtree(cls.xdg_cache_home)
        shutil.rmtree(cls.xdg_data_home)

    # Pylint apparently objects to test_method_name and method_name_T. The fuck?
    # pylint: disable=invalid-name,no-self-use
    def test_empty_url_construction_errors(self):
        """
        Constructing a subscription with a URL that is empty should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as exception:
            SUB.Subscription(url="", name="emptyConstruction", directory=TestSubscription.d)

        assert exception.value.desc == "No URL provided."

    # Pylint apparently objects to test_method_name and method_name_T. The fuck?
    # pylint: disable=invalid-name,no-self-use
    def test_none_url_construction_errors(self):
        """
        Constructing a subscription with a URL that is None should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as exception:
            SUB.Subscription(name="noneConstruction", directory=TestSubscription.d)

        assert exception.value.desc == "No URL provided."

    # Pylint apparently objects to test_method_name and method_name_T. The fuck?
    # pylint: disable=invalid-name
    def test_empty_name_construction_errors(self):
        """
        Constructing a subscription with a name that is empty should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(url="foo", name="", directory=TestSubscription.d)

        assert e.value.desc == "No name provided."

    # Pylint apparently objects to test_method_name and method_name_T. The fuck?
    # pylint: disable=invalid-name
    def test_none_name_construction_errors(self):
        """
        Constructing a subscription with a name that is None should throw a
        MalformedSubscriptionError.
        """
        with PT.raises(PE.MalformedSubscriptionError) as e:
            SUB.Subscription(url="foo", name=None, directory=TestSubscription.d)

        assert e.value.desc == "No name provided."

    # Pylint apparently objects to test_method_name and method_name_T. The fuck?
    # pylint: disable=invalid-name
    def test_get_feed_helper_fails_after_max(self):
        """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
        sub = SUB.Subscription(url=HTTP_302_ADDRESS, name="tooManyAttemptsTest",
                               directory=TestSubscription.d)

        # TODO tests need to be rewritten to check log output or something.
        sub.get_feed(attempt_count=SUB.MAX_RECURSIVE_ATTEMPTS+1)

        assert sub.feed_state.feed == {}
        assert sub.feed_state.entries == []

    def test_valid_temporary_redirect_succeeds(self):
        """
        If we are redirected temporarily to a valid RSS feed, we should successfully parse that
        feed and not change our url. The originally provided URL should be unchanged.
        """
        _test_url_helper(HTTP_302_ADDRESS, "302Test", HTTP_302_ADDRESS, HTTP_302_ADDRESS)

    def test_valid_permanent_redirect_succeeds(self):
        """
        If we are redirected permanently to a valid RSS feed, we should successfully parse that
        feed and change our url.  The originally provided URL should be unchanged
        """
        _test_url_helper(HTTP_301_ADDRESS, "301Test", RSS_ADDRESS, HTTP_301_ADDRESS)

    def test_not_found_fails(self):
        """If the URL is Not Found, we should not change the saved URL."""
        _test_url_helper(HTTP_404_ADDRESS, "404Test", HTTP_404_ADDRESS, HTTP_404_ADDRESS)

    def test_gone_fails(self):
        """If the URL is Gone, the current url should be set to None, and we should return None."""

        sub = SUB.Subscription(url=HTTP_410_ADDRESS, name="410Test", directory=TestSubscription.d)

        sub.use_backlog = True
        sub.backlog_limit = 1
        sub.use_title_as_filename = False

        sub.get_feed()

        # pylint: disable=protected-access
        assert sub._current_url is None
        assert sub._provided_url == HTTP_410_ADDRESS

    # TODO attempt to make tests that are less fragile/dependent on my website configuration/files.
    def test_attempt_download_backlog(self):
        """Should download full backlog by default."""
        sub = SUB.Subscription(url=RSS_ADDRESS, name="testfeed", directory=TestSubscription.d)

        sub.use_backlog = True
        sub.backlog_limit = 0
        sub.use_title_as_filename = False

        sub.attempt_update()

        assert len(sub.feed_state.entries) == 10
        for i in range(1, 9):
            _check_hi_contents(i, sub.directory)

    def test_attempt_download_partial_backlog(self):
        """Should download partial backlog if limit is specified."""
        sub = SUB.Subscription(url=RSS_ADDRESS, name="testfeed", backlog_limit=5,
                               directory=TestSubscription.d)

        # TODO find a cleaner way to set these.
        # Maybe Subscription should handle these attributes missing better?
        # Maybe have a cleaner way to hack them in in tests?
        sub.use_backlog = True
        sub.use_title_as_filename = False
        sub.attempt_update()

        assert len(sub.feed_state.entries) == 10
        for i in range(0, 4):
            _check_hi_contents(i, sub.directory)

def _test_urls_helper(self, given, name, expected_current, expected_provided):
    sub = SUB.Subscription(url=given, name=name, directory=TestSubscription.d)
    sub.get_feed()

    # pylint: disable=protected-access
    assert sub._current_url == expected_current
    assert sub._provided_url == expected_provided


def _check_hi_contents(n, directory):
    file_path = os.path.join(directory, "hi0{}.txt".format(n))
    with open(file_path, "r") as enclosure:
        data = enclosure.read().replace('\n', '')
        assert data == "hi"
