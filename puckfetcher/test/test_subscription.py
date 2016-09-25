"""Tests for the subscription module."""

import os
import string

from future.utils import viewitems

import feedparser
import pytest

import puckfetcher.error as PE
import puckfetcher.subscription as SUB

HERE = os.path.abspath(os.path.dirname(__file__))

RSS_TEST_HOST = "https://www.andrewmichaud.com/"
RSS_ADDRESS = RSS_TEST_HOST + "rss.xml"
LOCAL_RESOURCE_ADDRESS = "txt/hi.txt"
REMOTE_RESOURCE_ADDRESS = "https://www.andrewmichaud.com/txt/hi.txt"
HTTP_302_ADDRESS = RSS_TEST_HOST + "302"
HTTP_301_ADDRESS = RSS_TEST_HOST + "301"
HTTP_404_ADDRESS = RSS_TEST_HOST + "404"
HTTP_410_ADDRESS = RSS_TEST_HOST + "410"


def test_empty_url_cons(strdir):
    """
    Constructing a subscription with an empty URL should throw a MalformedSubscriptionError.
    """
    with pytest.raises(PE.MalformedSubscriptionError) as exception:
        SUB.Subscription(url="", name="emptyConstruction", directory=strdir)

    assert exception.value.desc == "No URL provided."

def test_none_url_cons(strdir):
    """
    Constructing a subscription with a URL that is None should throw a MalformedSubscriptionError.
    """
    with pytest.raises(PE.MalformedSubscriptionError) as exception:
        SUB.Subscription(name="noneConstruction", directory=strdir)

    assert exception.value.desc == "No URL provided."

def test_empty_name_cons(strdir):
    """
    Constructing a subscription with an empty name should throw a MalformedSubscriptionError.
    """
    with pytest.raises(PE.MalformedSubscriptionError) as exception:
        SUB.Subscription(url="foo", name="", directory=strdir)

    assert exception.value.desc == "No name provided."

def test_none_name_cons(strdir):
    """
    Constructing a subscription with a name that is None should throw a MalformedSubscriptionError.
    """
    with pytest.raises(PE.MalformedSubscriptionError) as exception:
        SUB.Subscription(url="foo", name=None, directory=strdir)

    assert exception.value.desc == "No name provided."

def test_get_feed_max(strdir):
    """If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
    sub = SUB.Subscription(url=HTTP_302_ADDRESS, name="tooManyAttemptsTest", directory=strdir)

    sub.get_feed(attempt_count=SUB.MAX_RECURSIVE_ATTEMPTS+1)

    assert sub.feed_state.feed == {}
    assert sub.feed_state.entries == []

def test_temporary_redirect(strdir):
    """
    If we are redirected temporarily to a valid RSS feed, we should successfully parse that
    feed and not change our url. The originally provided URL should be unchanged.
    """
    _test_url_helper(strdir, HTTP_302_ADDRESS, "302Test", HTTP_302_ADDRESS, HTTP_302_ADDRESS)

def test_permanent_redirect(strdir):
    """
    If we are redirected permanently to a valid RSS feed, we should successfully parse that
    feed and change our url. The originally provided URL should be unchanged.
    """
    _test_url_helper(strdir, HTTP_301_ADDRESS, "301Test", RSS_ADDRESS, HTTP_301_ADDRESS)

def test_not_found_fails(strdir):
    """If the URL is Not Found, we should not change the saved URL."""
    _test_url_helper(strdir, HTTP_404_ADDRESS, "404Test", HTTP_404_ADDRESS, HTTP_404_ADDRESS)

def test_gone_fails(strdir):
    """If the URL is Gone, the current url should be set to None, and we should return None."""

    sub = SUB.Subscription(url=HTTP_410_ADDRESS, name="410Test", directory=strdir)

    sub.use_backlog = True
    sub.backlog_limit = 1
    sub.use_title_as_filename = False

    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    sub.get_feed()

    assert sub.url is None
    assert sub.original_url == HTTP_410_ADDRESS

def test_new_attempt_update(strdir):
    """Attempting update on a new subscription (no backlog) should download nothing."""
    test_dir = strdir
    sub = SUB.Subscription(url="foo", name="foo", directory=test_dir)
    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    sub.attempt_update()
    assert len(os.listdir(test_dir)) == 0

def test_attempt_update_new_entry(strdir):
    """Attempting update on a podcast with a new entry should download the new entry only."""
    test_dir = strdir
    sub = SUB.Subscription(url=RSS_ADDRESS, name="bar", directory=test_dir)
    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    assert len(os.listdir(test_dir)) == 0

    sub.feed_state.latest_entry_number = 9

    sub.attempt_update()
    assert sub.feed_state.latest_entry_number == 10
    assert len(os.listdir(test_dir)) == 1
    _check_hi_contents(0, test_dir)

def test_attempt_download_backlog(strdir):
    """Should download full backlog if backlog limit set to None."""
    sub = SUB.Subscription(url=RSS_ADDRESS, name="testfeed", directory=strdir)
    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    sub.use_backlog = True
    sub.backlog_limit = None
    sub.use_title_as_filename = False

    sub.attempt_update()

    assert len(sub.feed_state.entries) == 10
    assert len(os.listdir(sub.directory)) == 10
    for i in range(1, 9):
        _check_hi_contents(i, sub.directory)

def test_attempt_download_partial_backlog(strdir):
    """Should download partial backlog if limit is specified."""
    sub = SUB.Subscription(url=RSS_ADDRESS, name="testfeed", backlog_limit=5, directory=strdir)

    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    # TODO find a cleaner way to set these.
    # Maybe Subscription should handle these attributes missing better?
    # Maybe have a cleaner way to hack them in in tests?
    sub.use_backlog = True
    sub.backlog_limit = 4
    sub.use_title_as_filename = False
    sub.attempt_update()

    for i in range(0, 4):
        _check_hi_contents(i, sub.directory)

def test_mark(sub_with_entries):
    """Should mark subscription entries correctly."""
    assert len(sub_with_entries.feed_state.entries) > 0

    test_nums = [2, 3, 4, 5]
    bad_nums = [-1, -12, 10000]
    all_nums = bad_nums + test_nums + bad_nums

    for entry_downloaded in sub_with_entries.feed_state.entries_state_dict.values():
        assert not entry_downloaded

    sub_with_entries.mark(all_nums)

    assert len(sub_with_entries.feed_state.entries_state_dict) > 0
    for (zero_indexed_key, value) in viewitems(sub_with_entries.feed_state.entries_state_dict):
        if zero_indexed_key+1 in test_nums:
            assert value
        else:
            assert not value

def test_unmark(sub_with_entries):
    """Should unmark subscription entries correctly."""
    assert len(sub_with_entries.feed_state.entries) > 0
    for key in sub_with_entries.feed_state.entries_state_dict:
        sub_with_entries.feed_state.entries_state_dict[key] = True

    test_nums = [2, 3, 4, 5]
    bad_nums = [-1, -12, 10000]
    all_nums = bad_nums + test_nums + bad_nums

    sub_with_entries.unmark(all_nums)

    assert len(sub_with_entries.feed_state.entries_state_dict) > 0
    for (zero_indexed_key, value) in viewitems(sub_with_entries.feed_state.entries_state_dict):
        if zero_indexed_key+1 in test_nums:
            assert not value
        else:
            assert value

# Helpers.
def _test_url_helper(strdir, given, name, expected_current, expected_original):
    sub = SUB.Subscription(url=given, name=name, directory=strdir)

    sub.downloader = generate_fake_downloader()
    sub.parser = generate_feedparser()

    sub.get_feed()

    assert sub.url == expected_current
    assert sub.original_url == expected_original


def _check_hi_contents(filename_num, directory):
    file_path = os.path.join(directory, "hi0{}.txt".format(filename_num))
    with open(file_path, "r") as enclosure:
        data = enclosure.read().replace('\n', '')
        assert data == "hi"

def generate_fake_downloader():
    """Fake downloader for test purposes."""

    def _downloader(url=None, dest=None):
        contents = "hi"

        open(dest, "a").close()
        # per http://stackoverflow.com/a/20943461
        with open(dest, "w") as stream:
            stream.write(contents)
            stream.flush()

    return _downloader

def generate_feedparser():
    """Feedparser wrapper without rate_limiting, for testing."""

    def _rate_limited_parser(url, etag, last_modified):

        return feedparser.parse(url, etag=etag, modified=last_modified)

    return _rate_limited_parser


# Fixtures.
@pytest.fixture(scope="function")
def strdir(tmpdir):
    """Create temp directory, in string format."""
    return str(tmpdir.mkdir("foo"))


@pytest.fixture(scope="function")
def sub(strdir):
    """Create a test subscription."""
    test_sub = SUB.Subscription(url="test", name="test", directory=strdir)

    return test_sub

@pytest.fixture(scope="function")
def sub_with_entries(sub):
    """Create a test subscription with faked entries."""
    sub.feed_state.entries = list(range(0, 20))

    sub.downloader = generate_fake_downloader()

    return sub
