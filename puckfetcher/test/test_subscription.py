"""Tests for the subscription module."""
import os
import shutil
from typing import Any, Callable, Dict, Mapping

import stagger
import pytest

import puckfetcher.error as error
import puckfetcher.subscription as subscription

RSS_ADDRESS = "valid"
PERM_REDIRECT = "301"
TEMP_REDIRECT = "302"
NOT_FOUND = "404"
GONE = "410"

ERROR_CASES = [TEMP_REDIRECT, PERM_REDIRECT, NOT_FOUND, GONE]


def test_empty_url_cons(strdir: str) -> None:
    """
    Constructing a subscription with an empty URL should return a None object.
    """
    with pytest.raises(error.MalformedSubscriptionError) as exception:
        subscription.Subscription(url="", name="emptyConstruction", directory=strdir)

    assert exception.value.desc == "URL '' is None or empty - can't create subscription."

def test_none_url_cons(strdir: str) -> None:
    """
    Constructing a subscription with a URL that is None should throw a MalformedSubscriptionError.
    """
    with pytest.raises(error.MalformedSubscriptionError) as exception:
        subscription.Subscription(name="noneConstruction", directory=strdir)

    assert exception.value.desc == "URL 'None' is None or empty - can't create subscription."

def test_empty_name_cons(strdir: str) -> None:
    """
    Constructing a subscription with an empty name should throw a MalformedSubscriptionError.
    """
    with pytest.raises(error.MalformedSubscriptionError) as exception:
        subscription.Subscription(url="foo", name="", directory=strdir)

    assert exception.value.desc == "Name '' is None or empty - can't create subscription."

def test_none_name_cons(strdir: str) -> None:
    """
    Constructing a subscription with a name that is None should throw a MalformedSubscriptionError.
    """
    with pytest.raises(error.MalformedSubscriptionError) as exception:
        subscription.Subscription(url="foo", name=None, directory=strdir)

    assert exception.value.desc == "Name 'None' is None or empty - can't create subscription."

def test_get_feed_max(strdir: str) -> None:
    """ If we try more than MAX_RECURSIVE_ATTEMPTS to retrieve a URL, we should fail."""
    test_sub = subscription.Subscription(url=PERM_REDIRECT, name="tooManyAttemptsTest",
                                         directory=strdir)

    test_sub.get_feed(attempt_count=subscription.MAX_RECURSIVE_ATTEMPTS + 1)

    assert test_sub.feed_state.feed == {}
    assert test_sub.feed_state.entries == []

def test_temporary_redirect(strdir: str) -> None:
    """
    If we are redirected temporarily to a valid RSS feed, we should successfully parse that
    feed and not change our url. The originally provided URL should be unchanged.
    """
    _test_url_helper(strdir, TEMP_REDIRECT, "302Test", TEMP_REDIRECT, TEMP_REDIRECT)

def test_permanent_redirect(strdir: str) -> None:
    """
    If we are redirected permanently to a valid RSS feed, we should successfully parse that
    feed and change our url. The originally provided URL should be unchanged.
    """
    _test_url_helper(strdir, PERM_REDIRECT, "301Test", "", PERM_REDIRECT)

def test_not_found_fails(strdir: str) -> None:
    """If the URL is Not Found, we should not change the saved URL."""
    _test_url_helper(strdir, NOT_FOUND, "404Test", NOT_FOUND, NOT_FOUND)

def test_gone_fails(strdir: str) -> None:
    """If the URL is Gone, the current url should be set to None, and we should return None."""
    test_sub = subscription.Subscription(url=GONE, name="410Test", directory=strdir)

    test_sub.settings["backlog_limit"] = 1
    test_sub.settings["use_title_as_filename"] = False

    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    test_sub.get_feed()

    assert test_sub.url is ""
    assert test_sub.original_url == GONE

def test_new_attempt_update(strdir: str) -> None:
    """Attempting update on a new subscription (no backlog) should download nothing."""
    test_dir = strdir
    test_sub = subscription.Subscription(url="foo", name="foo", directory=test_dir)
    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    test_sub.attempt_update()
    assert len(os.listdir(test_dir)) == 0

def test_attempt_update_new_entry(strdir: str) -> None:
    """Attempting update on a podcast with a new entry should download the new entry only."""
    test_dir = strdir
    test_sub = subscription.Subscription(url=RSS_ADDRESS, name="bar", directory=test_dir)
    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    assert len(os.listdir(test_dir)) == 0

    test_sub.feed_state.latest_entry_number = 9

    test_sub.attempt_update()
    assert test_sub.feed_state.latest_entry_number == 10
    assert len(os.listdir(test_dir)) == 1

def test_attempt_download_backlog(strdir: str) -> None:
    """Should download full backlog if backlog limit set to None."""
    test_sub = subscription.Subscription(url=RSS_ADDRESS, name="testfeed", directory=strdir)
    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    test_sub.settings["backlog_limit"] = None
    test_sub.settings["use_title_as_filename"] = False

    test_sub.attempt_update()

    assert len(test_sub.feed_state.entries) == 10
    assert len(os.listdir(test_sub.directory)) == 10

def test_attempt_download_partial_backlog(strdir: str) -> None:
    """Should download partial backlog if limit is specified."""
    test_sub = subscription.Subscription(url=RSS_ADDRESS, name="testfeed", directory=strdir)

    test_sub.settings["backlog_limit"] = 5

    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    # TODO find a cleaner way to set these.
    # Maybe test_subscription should handle these attributes missing better?
    # Maybe have a cleaner way to hack them in in tests?
    test_sub.settings["backlog_limit"] = 4
    test_sub.settings["use_title_as_filename"] = False
    test_sub.attempt_update()

def test_mark(sub_with_entries: subscription.Subscription) -> None:
    """Should mark subscription entries correctly."""
    assert len(sub_with_entries.feed_state.entries) > 0

    test_nums = [2, 3, 4, 5]
    bad_nums = [-1, -12, 10000]
    all_nums = bad_nums + test_nums + bad_nums

    for test_num in test_nums:
        assert test_num not in sub_with_entries.feed_state.entries_state_dict

    sub_with_entries.mark(all_nums)

    assert len(sub_with_entries.feed_state.entries_state_dict) > 0
    for test_num in test_nums:
        zero_indexed_num = test_num - 1
        assert zero_indexed_num in sub_with_entries.feed_state.entries_state_dict
        assert sub_with_entries.feed_state.entries_state_dict[zero_indexed_num]

    for bad_num in bad_nums:
        assert bad_num not in sub_with_entries.feed_state.entries_state_dict

def test_unmark(sub_with_entries: subscription.Subscription) -> None:
    """Should unmark subscription entries correctly."""
    assert len(sub_with_entries.feed_state.entries)> 0

    test_nums = [2, 3, 4, 5]
    bad_nums = [-1, -12, 10000]
    all_nums = bad_nums + test_nums + bad_nums

    for num in test_nums:
        sub_with_entries.feed_state.entries_state_dict[num - 1] = True

    sub_with_entries.unmark(all_nums)

    assert len(sub_with_entries.feed_state.entries_state_dict) > 0
    for test_num in test_nums:
        zero_indexed_num = test_num - 1
        assert zero_indexed_num in sub_with_entries.feed_state.entries_state_dict
        assert not sub_with_entries.feed_state.entries_state_dict[zero_indexed_num]

    for bad_num in bad_nums:
        assert bad_num not in sub_with_entries.feed_state.entries_state_dict

def test_url_with_qparams() -> None:
    """Test that the _get_dest helper handles query parameters properly."""
    test_sub = subscription.Subscription(url="test", name="test", directory="test")

    test_sub.settings["use_title_as_filename"] = True

    # pylint: disable=protected-access
    filename = test_sub._get_dest("https://www.example.com?foo=1/bar.mp3?baz=2", "puck", "/test")
    assert filename == "/test/puck.mp3"

    test_sub.settings["use_title_as_filename"] = False

    # pylint: disable=protected-access
    filename = test_sub._get_dest("https://www.example.com?foo=1/bar.mp3?baz=2", "puck", "/test")
    assert filename == "/test/bar.mp3"

def test_url_sanitize() -> None:
    """
    Test that the _get_dest helper sanitizes correctly on non-Windows. Only / should need to be
    replaced
    """
    test_sub = subscription.Subscription(url="test", name="test", directory="test")

    test_sub.settings["use_title_as_filename"] = True

    # pylint: disable=protected-access
    filename = test_sub._get_dest("https://www.example.com?foo=1/bar.mp3?baz=2", "p/////uck",
                                  "/test")
    assert filename == "/test/p-----uck.mp3"

    # pylint: disable=protected-access
    filename = test_sub._get_dest("https://www.example.com?foo=1/bar.mp3?baz=2", "p🤔🤔🤔🤔uck",
                                  "/test")
    assert filename == "/test/p🤔🤔🤔🤔uck.mp3"

    # pylint: disable=protected-access
    filename = test_sub._get_dest("https://www.example.com?foo=1/bar.mp3?baz=2", "p*%$^\\1uck",
                                  "/test")
    assert filename == "/test/p*%$^\\1uck.mp3"

def test_tagging(strdir: str) -> None:
    test_sub = subscription.Subscription(url=RSS_ADDRESS, name="testfeed", directory=strdir)

    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    metadata = {
        "name": test_sub.metadata["name"],
        "artist": "hello-artist",
        "album": test_sub.metadata["name"],
        "album_artist": "hello-artist-album",
    }

    test_sub.metadata = metadata

    test_sub.settings["backlog_limit"] = 4
    test_sub.settings["set_tags"] = True

    test_sub.attempt_update()

    for i in range(0, 4):
        _check_tag_presence(i, test_sub.directory, metadata=metadata)

def test_tagging_skipped(strdir: str) -> None:
    test_sub = subscription.Subscription(url=RSS_ADDRESS, name="testfeed", directory=strdir)

    test_sub.downloader = generate_fake_downloader(filetype="m4a")
    test_sub.parser = generate_feedparser(filetype="m4a")

    test_sub.settings["backlog_limit"] = 4
    test_sub.settings["set_tags"] = True

    test_sub.attempt_update()

    for i in range(0, 4):
        _check_tag_absence(i, test_sub.directory)

# Helpers.
def _test_url_helper(strdir: str, given: str, name: str, expected_current: str,
                     expected_original: str,
                     ) -> None:
    test_sub = subscription.Subscription(url=given, name=name, directory=strdir)

    test_sub.downloader = generate_fake_downloader()
    test_sub.parser = generate_feedparser()

    test_sub.get_feed()

    assert test_sub.url == expected_current
    assert test_sub.original_url == expected_original

def _check_tag_absence(
    filename_num: int,
    directory: str,
) -> None:
    file_path = os.path.join(directory, f"hi0{filename_num}.m4a")
    try:
        tag = stagger.read_tag(file_path)
    except stagger.errors.NoTagError as e:
        return

    pytest.fail("Tag should not be present for this podcast!")

def _check_tag_presence(
    filename_num: int,
    directory: str,
    metadata: Mapping[str, str]={},
) -> None:
    file_path = os.path.join(directory, f"hi0{filename_num}.mp3")
    try:
        tag = stagger.read_tag(file_path)
    except stagger.errors.NoTagError as e:
        pytest.fail("Tag should be present for this podcast!")

    if tag.artist != metadata["artist"]:
        pytest.fail(f"artist tag should be {metadata['artist']} but is actually {tag.artist}")

    if tag.album != metadata["album"]:
        pytest.fail(f"album tag should be {metadata['album']} but is actually {tag.album}")

    if tag.album_artist != metadata["album_artist"]:
        pytest.fail(
            f"album_artist tag should be {metadata['album_artist']}, "
            f"but is actually {tag.album_artist}"
        )

def generate_fake_downloader(
    *,
    filetype: str="mp3",

) -> Callable[[str, str], None]:
    """Fake downloader for test purposes."""

    def _mp3_downloader(url: str, dest: str) -> None:
        HERE = os.path.dirname(os.path.realpath(__file__))

        shutil.copyfile(
            os.path.join(
                HERE,
                "test.mp3",
            ),
            dest,
        )

        tag = stagger.Tag24()
        tag.write(dest)

    def _m4a_downloader(url: str, dest: str) -> None:
        HERE = os.path.dirname(os.path.realpath(__file__))

        shutil.copyfile(
            os.path.join(
                HERE,
                "test.m4a",
            ),
            dest,
        )

    if filetype == "mp3":
        return _mp3_downloader
    else:
        return _m4a_downloader

def generate_feedparser(
    *,
    filetype: str="mp3",
) -> Callable[[str, Any, Any], Dict[str, Any]]:
    """Feedparser wrapper without rate_limiting, for testing."""

    # pylint: disable=unused-argument
    def _fake_parser(url: str, etag: Any, last_modified: Any) -> Dict[str, Any]:

        fake_parsed: Dict[str, Any] = {}
        entries = []
        href = ""
        for i in range(0, 10):
            entry: Dict[str, Any] = {}
            entry["title"] = "hi"
            entry["metadata"] = {}
            entry["metadata"]["title"] = "hi"
            entry["metadata"]["artist"] = "hi-artist"
            entry["metadata"]["album"] = "hi-album"
            entry["metadata"]["artist_album"] = "hi-artist-album"
            entry["enclosures"] = [{"href": f"hi0{i}.{filetype}"}]

            entries.append(entry)

        if url in ERROR_CASES:
            status = int(url)

            if url == PERM_REDIRECT or url == TEMP_REDIRECT:
                href = RSS_ADDRESS

        else:
            status = 200

        fake_parsed["entries"] = entries
        fake_parsed["href"] = href
        fake_parsed["status"] = status

        return fake_parsed

    return _fake_parser


# Fixtures.
@pytest.fixture(scope="function")
def strdir(tmpdir: Any) -> str:
    """Create temp directory, in string format."""
    return str(tmpdir.mkdir("foo"))

@pytest.fixture(scope="function")
def sub(strdir: str) -> subscription.Subscription:
    """Create a test subscription."""
    test_sub = subscription.Subscription(url="test", name="test", directory=strdir)

    return test_sub

@pytest.fixture(scope="function")
def sub_with_entries(sub: subscription.Subscription) -> subscription.Subscription:
    """Create a test subscription with faked entries."""
    sub.feed_state.entries = list(range(0, 20))

    sub.downloader = generate_fake_downloader()

    return sub
