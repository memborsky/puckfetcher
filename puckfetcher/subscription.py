import copy
from enum import Enum
import logging
import os
import pkg_resources
import textwrap

from clint.textui import progress
import feedparser
import requests

import puckfetcher.error as E
import puckfetcher.util as U

MAX_RECURSIVE_ATTEMPTS = 10
# TODO can we retrieve this only once?
VERSION = pkg_resources.require(__package__)[0].version
# TODO pull url from setup.py or something
USER_AGENT = __package__ + "/" + VERSION + " +https://github.com/andrewmichaud/puckfetcher"

logger = logging.getLogger("root")


# Public subscription helpers (not part of class).
def encode_subscription(obj):
    """Encode subscription as dictionary for msgpack."""
    return {"_current_url": obj._current_url,
            "_provided_url": obj._provided_url,
            "backlog_limit": obj.backlog_limit,
            "directory": obj.directory,
            "download_backlog": obj.download_backlog,
            "entries": obj.entries,
            "feed": obj.feed,
            "latest_entry_number": obj.latest_entry_number,
            "name": obj.name}


def decode_subscription(obj):
    """Decode subscription from dictionary."""
    # TODO find out how to use __new__ or whatever the generic constructor is in a way that will
    # work in Python 2 and 3.
    sub = Subscription(url=obj["_provided_url"], name=obj["name"])

    sub._current_url = obj["_current_url"]
    sub._provided_url = obj["_provided_url"]
    sub.backlog_limit = obj["backlog_limit"]
    sub.directory = obj["directory"]
    sub.download_backlog = obj["download_backlog"]
    sub.entries = obj["entries"]
    sub.feed = obj["feed"]
    sub.latest_entry_number = obj["latest_entry_number"]
    sub.name = obj["name"]
    return sub


def parse_from_user_yaml(sub_yaml):
    """Parse YAML user-provided subscription into a subscription object."""

    name = sub_yaml.get("name", "Generic Podcast")

    if sub_yaml.get("url", None) is None:
        raise E.InvalidConfigError("No URL provided, URL is mandatory!")
    else:
        url = sub_yaml["url"]

    # TODO this needs cleaning.
    download_backlog = sub_yaml.get("download_backlog", True)
    backlog_limit = sub_yaml.get("backlog_limit", None)
    directory = sub_yaml.get("directory", None)

    # TODO add ability to pretty-print subscription and print here.
    return Subscription(name=name, url=url, download_backlog=download_backlog,
                        backlog_limit=backlog_limit, directory=directory)


# TODO describe field members, function parameters in docstrings.
class Subscription():
    """Object describing a podcast subscription."""

    # TODO Specify production vs test "properly", somehow.
    def __init__(self, url=None, name=None, directory=None, download_backlog=True,
                 backlog_limit=None, production=True, latest_entry_number=0):

        self.production = production
        logger.info("Running in production mode: {0}.".format(production))

        self.latest_entry_number = latest_entry_number
        logger.info("Latest entry downloaded: {0}.".format(latest_entry_number))

        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if (url is None or url == ""):
            raise E.MalformedSubscriptionError("No URL provided.")
        else:
            logger.debug("Storing provided url {0}.".format(url))
            self._provided_url = copy.deepcopy(url)
            self._current_url = copy.deepcopy(url)

        # Maintain name of podcast.
        if (name is None or name == ""):
            raise E.MalformedSubscriptionError("No name provided.")
        else:
            logger.debug("Provided name {0}.".format(name))
            self.name = name

        # TODO allow multiple downloads at once.

        # Use etag and last-modified to detect when we have the latest feed.
        # Store latest feed (and entries separately, for convenience.
        self.etag = None
        self.last_modified = None
        self.feed = None
        self.entries = None
        self.last_status = None

        self._handle_directory(directory)

        self.download_backlog = download_backlog
        logger.debug("Set to download backlog: {0}.".format(download_backlog))

        self.backlog_limit = backlog_limit
        logger.debug("Backlog limit: {0}.".format(backlog_limit))

        feedparser.USER_AGENT = USER_AGENT
        logger.debug("User agent: {0}.".format(USER_AGENT))

        # Provide rate limiting.
        self.get_feed = U.rate_limited(self.production, 120, self.name)(self.get_feed)
        self.download_file = U.rate_limited(self.production, 60, self.name)(self.download_file)

    class UpdateResult(Enum):
        SUCCESSFUL_UPDATE = 1
        NO_UPDATE = 0
        UPDATE_FAILURE = -1

    # "Public" functions.
    def attempt_update(self):
        """Attempt to download new entries for a subscription."""
        feed_get_result = self.get_feed()
        if feed_get_result == self.UpdateResult.NO_UPDATE:
            logger.info("Feed for {0} was not updated.".format(self.name))
            return False

        elif feed_get_result == self.UpdateResult.UPDATE_FAILURE:
            logger.error("Feed for {0} encountered errors while updating.".format(self.name))
            return False

        logger.info("Feed for {0} was updated.".format(self.name))

        # Check how many entries we've missed.
        if self.entries is None:
            logger.error("No entries for {0}, cannot attempt update.".format(self.name))
            return False

        number_to_download = 0
        number_feeds = len(self.entries)
        # TODO I've cleaned up this logic before, but it's worth trying again.
        if self.latest_entry_number == 0:
            if self.download_backlog:
                if self.backlog_limit is None:
                    number_to_download = number_feeds
                    logger.info(textwrap.dedent(
                        """\
                        Backlog limit for {0} is set to None.
                        Interpreting as "No Limit" and downloading full backlog ({1} entries).\
                        """.format(self.name, number_to_download)))

                elif self.backlog_limit < 0:
                    logger.error(textwrap.dedent(
                        """\
                        Invalid backlog limit {0}, downloading nothing.\
                        """.format(self.backlog_limit)))
                    return False

                elif self.backlog_limit <= number_feeds:
                    number_to_download = self.backlog_limit
                    logger.info(textwrap.dedent(
                        """\
                        Backlog limit for {0} is set to {1}, less than number of feeds {2}.
                        Downloading {1} entries.\
                        """.format(self.name, self.backlog_limit, number_feeds,
                                   number_to_download)))

                else:
                    number_to_download = number_feeds
                    logger.info(textwrap.dedent(
                        """\
                        Backlog limit for {0} is set to {1}, greater than number of feeds {2}.
                        Downloading only {1} entries.\
                        """.format(self.name, self.backlog_limit, number_feeds,
                                   number_to_download)))

            else:
                self.latest_entry_number = number_feeds
                logger.info(textwrap.dedent(
                    """\
                    Download backlog for {0} is not set.
                    Downloading nothing, but setting number downloaded to {1}.\
                    """.format(self.name, self.latest_entry_number)))

        elif self.latest_entry_number < number_feeds:
            number_to_download = number_feeds - self.latest_entry_number
            logger.info(textwrap.dedent(
                """\
                Number of downloaded feeds for {0} is {1}, {2} less than feed entry count {3}.
                Downloading {1} entries.\
                """.format(self.name, self.latest_entry_number, number_to_download,
                           number_feeds)))

        else:
            logger.info(textwrap.dedent(
                """\
                Number downloaded for {0} matches feed entry count {1}.
                Nothing to download.\
                """.format(self.name, number_feeds)))
            return True

        self.download_entry_files(oldest_entry_age=number_to_download-1)

        return True

    def download_entry_files(self, oldest_entry_age=-1):
        """
        Download feed enclosure(s) for all entries newer than the given oldest entry age to object
        directory.
        """

        # Downloading feeds oldest first makes the most sense for RSS feeds (IMO), so we do that.
        for entry_age in range(oldest_entry_age, -1, -1):
            if entry_age < 0 or entry_age >= len(self.entries):
                logger.error("Given invalid entry age {0} to for {1}.".format(entry_age,
                                                                              self.name))
                return

            logger.info("Downloading entry {0} for {1}.".format(entry_age, self.name))

            entry = self.entries[entry_age]
            enclosures = entry.enclosures
            logger.info("There are {0} enclosures for entry with age {1}.".format(len(enclosures),
                                                                                  entry_age))

            # Create directory just for enclosures for this entry if there are many.
            directory = self.directory
            if len(enclosures) > 1:
                directory = os.path.join(directory, entry.title)
                logger.debug(textwrap.dedent(
                    """\
                    More than 1 enclosure for entry {0}, creating directory {1} to store them.\
                    """.format(entry.title, directory)))

            for i, enclosure in enumerate(enclosures):
                logger.info("Handling enclosure {0} of {1}.".format(i+1, len(enclosures)))

                url = enclosure.href
                logger.info("Extracted url {0}.".format(url))

                filename = url.split('/')[-1]
                file_location = os.path.join(directory, filename)

                # If there is a file with the name we intend to save to, assume the podcast has
                # been downloaded already.
                if not os.path.isfile(file_location):
                    logger.info("Saving file for enclosure {0} to {1}.".format(i+1, file_location))
                    self.download_file(url, file_location)

                else:
                    logger.info(textwrap.dedent(
                        """\
                        File {0} already exists, assuming already downloaded and not overwriting.\
                        """.format(file_location)))

            self.latest_entry_number += 1
            logger.info(textwrap.dedent(
                """\
                Have downloaded {0} entries for subscription {1}.\
                """.format(self.latest_entry_number, self.name)))

    def download_file(self, url, file_location):
        """Download a file. Wrapper around the *actual* write to allow targeted rate limiting."""
        # TODO should maybe be defined for class or something.
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, stream=True)

        total_length = int(response.headers.get("content-length"))
        expected_size = (total_length / 1024) + 1
        chunks = response.iter_content(chunk_size=1024)

        # per http://stackoverflow.com/a/20943461
        with open(file_location, "wb") as f:
            for chunk in progress.bar(chunks, expected_size=expected_size):
                if chunk:
                    f.write(chunk)
                    f.flush()

    def get_feed(self, attempt_count=0):
        """Get RSS structure for this subscription. Return None if an error occurs."""
        return self._get_feed_helper(attempt_count=attempt_count)

    def update_directory(self, directory, config_dir):
        """Update directory for this subscription if a new one is provided."""
        if directory is None or directory == "":
            raise E.InvalidConfigError(desc=textwrap.dedent(
                """\
                Provided invalid sub directory '{0}' for '{1}'.\
                """.format(directory, self.name)))

        if self.directory != directory:
            # NOTE This may not be fully portable. Should work at least on OSX and Linux.
            # Assume a directory starting with the separator is meant to be absolute.
            # Assume no responsibility for a bad path.
            # TODO assume responsibility.
            if directory[0] == os.path.sep:
                self.directory = directory

            else:
                self.directory = os.path.join(config_dir, directory)

    def update_url(self, url):
        """Update url for this subscription if a new one is provided."""
        if url != self._provided_url:
            self._provided_url = copy.deepcopy(url)

        self._current_url = copy.deepcopy(url)

    # "Private" functions (messy internals).
    def _handle_directory(self, directory):
        """Assign directory if none was given, and create directory if necessary."""
        if directory is None:
            self.directory = U.DATA_DIR
            logger.debug("No directory provided, defaulting to {0}.".format(self.directory))

        else:
            self.directory = directory
            logger.debug("Provided directory {0}.".format(directory))

            if not os.path.isdir(self.directory):
                logger.debug("Directory {0} does not exist, creating it.".format(directory))
                os.makedirs(self.directory)

    def _get_feed_helper(self, attempt_count):
        """
        Helper method to get feed text that can be called recursively. Limited to
        MAX_RECURSIVE_ATTEMPTS attempts.
        Return whether we successfully got a new feed.
        """

        if attempt_count > MAX_RECURSIVE_ATTEMPTS:
            logger.error(textwrap.dedent(
                """\
                Too many recursive attempts ({0}) to get feed for subscription {1}, cancelling.\
                """.format(attempt_count, self.name)))
            return self.UpdateResult.UPDATE_FAILURE

        if self._current_url is None or self._current_url == "":
            logger.error(textwrap.dedent(
                """\
                URL is empty or None, cannot get feed text for subscription {0}.
                Last HTTP status was {1}.\
                """.format(self.name, self.last_status)))
            return self.UpdateResult.UPDATE_FAILURE

        logger.info(textwrap.dedent(
            """\
            Getting entries (attempt {0}) for subscription {1} with URL {2}.\
            """.format(attempt_count, self.name, self._current_url)))

        parsed = self._feedparser_parse_with_options()
        if parsed is None:
            logger.error("Feedparser parse failed, aborting.")
            return False

        # Detect some kinds of HTTP status codes signalling failure.
        http_says_continue = self._handle_http_codes(attempt_count, parsed)
        if not http_says_continue:
            logger.error("Ran into HTTP error, aborting..")
            return False

        self.feed = parsed.get("feed", {})
        self.entries = parsed.get("entries", [])

    def _feedparser_parse_with_options(self):
        """Perform a feedparser parse, providing arguments (like etag) we might want it to use."""
        parsed = feedparser.parse(self._current_url, etag=self.etag, modified=self.last_modified)
        self.etag = parsed.get("etag", None)
        self.last_modified = parsed.get("last_modified", None)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # Feedparser documentation indicates that you can always call getMessage, but it's
            # possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            logger.error(textwrap.dedent(
                """\
                Received bozo exception {0}. Unable to retrieve feed with URL {1} for {2}.\
                """.format(msg, self._current_url, self.name)))
            return None

        return parsed

    def _handle_http_codes(self, attempt_count, parsed):
        """
        Handle any http codes that might result from parsing a feed url.
        Return True if we should continue with parsing, or False if we should not.
        """
        status = parsed.status
        if status == requests.codes.NOT_FOUND:
            logger.error(textwrap.dedent(
                """\
                Saw status {0}, unable to retrieve feed text for {2}.
                Current URL {1} for {2} will be preserved and checked again on next attempt.\
                """.format(status, self._current_url, self.name)))
            return self.UpdateResult.UPDATE_FAILURE

        # TODO hook for dealing with password-protected feeds.
        elif status in [requests.codes.UNAUTHORIZED, requests.codes.GONE]:
            logger.error(textwrap.dedent(
                """\
                Saw status {0}, unable to retrieve feed text for {2}.
                Clearing stored URL {0} from _current_url for {2}.
                Originally provided URL {1} will be maintained at _provided_url, but will no longer
                be used.
                Please provide new URL and authorization for subscription {2}.\
                """.format(status, self._current_url, self.name)))

            self._current_url = None
            return self.UpdateResult.UPDATE_FAILURE

        # Handle redirecting errors
        if status in [requests.codes.MOVED_PERMANENTLY, requests.codes.PERMANENT_REDIRECT]:
            logger.warning(textwrap.dedent(
                """\
                Saw status {0} indicating permanent URL change.
                Changing stored URL {1} for {2} to {3} and attempting get with new URL.\
                """.format(status, self._current_url, self.name, parsed.href)))

            self._current_url = parsed.href
            return self._get_feed_helper(attempt_count+1)

        elif status in [requests.codes.FOUND,
                        requests.codes.SEE_OTHER,
                        requests.codes.TEMPORARY_REDIRECT]:
            logger.warning(textwrap.dedent(
                """\
                Saw status {0} indicating temporary URL change.
                Attempting with new URL {1}. Stored URL {2} for {3} will be unchanged.\
                """.format(status, parsed.href, self._current_url, self.name)))

            old_url = self._current_url
            self._current_url = parsed.href
            result = self._get_feed_helper(attempt_count+1)
            self._current_url = old_url

            return result

        if status == requests.codes.NOT_MODIFIED:
            logger.error(textwrap.dedent(
                """\
                Saw status {0} - NOT MODIFIED. Have latest feed for {0}, nothing to do.
                """.format(status, self.name)))
            return self.UpdateResult.NO_UPDATE

        elif status != 200:
            logger.warning(textwrap.dedent(
                """\
                Saw unhandled non-200 status {0}. Attempting feed retrieve with URL {1} for {2}
                anyways.\
                """.format(status, self._current_url, self.name)))
            return self._get_feed_helper(attempt_count+1)

        logger.info("Saw status {0} - OK, all is well.")
        self.feed = parsed.get("feed", {})
        self.entries = parsed.get("entries", [])
        return self.UpdateResult.SUCCESSFUL_UPDATE

    def _feedparser_parse_with_options(self):
        """
        Perform a feedparser parse, providing arguments (like etag) we might want it to use.
        Don't provide etag/last_modified if the last get was unsuccessful.
        """
        if self.feed is None:
            parsed = feedparser.parse(self._current_url)
        else:
            parsed = feedparser.parse(self._current_url, etag=self.etag,
                                      modified=self.last_modified)
            self.etag = parsed.get("etag", None)
            self.last_modified = parsed.get("last_modified", None)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # Feedparser documentation indicates that you can always call getMessage, but it's
            # possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            logger.error(textwrap.dedent(
                """\
                Received bozo exception {0}. Unable to retrieve feed with URL {1} for {2}.\
                """.format(msg, self._current_url, self.name)))
            return None

        return parsed

    def __eq__(self, rhs):
        if isinstance(rhs, Subscription):
            if self.name != rhs.name:
                return False
            elif self._current_url != rhs._current_url:
                return False
            elif self._provided_url != rhs._provided_url:
                return False
            elif self.latest_entry_number != rhs.latest_entry_number:
                return False
            elif self.directory != rhs.directory:
                return False
            elif self.download_backlog != rhs.download_backlog:
                return False
            elif self.backlog_limit != rhs.backlog_limit:
                return False

            return True
        else:
            return False

    def __ne__(self, rhs):
        return not self.__eq__(rhs)

    def __repr__(self):
        return str(encode_subscription(self))
