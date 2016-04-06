"""
Module for a subscription object, which manages a podcast URL, name, and information about how
many episodes of the podcast we have.
"""
import copy
import logging
import os
import textwrap
from enum import Enum

import feedparser
import requests

import puckfetcher.constants as CONSTANTS
import puckfetcher.error as E
import puckfetcher.util as Util


MAX_RECURSIVE_ATTEMPTS = 10
HEADERS = {"User-Agent": CONSTANTS.USER_AGENT}

LOGGER = logging.getLogger("root")


# TODO describe field members, function parameters in docstrings.
# pylint: disable=too-many-instance-attributes
class Subscription(object):
    """Object describing a podcast subscription."""

    # pylint: disable=too-many-arguments
    def __init__(self, url=None, name=None, directory=None, download_backlog=True,
                 backlog_limit=None):

        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if url is None or url == "":
            raise E.MalformedSubscriptionError("No URL provided.")
        else:
            LOGGER.debug("Storing provided url '%s'.", url)
            self._provided_url = copy.deepcopy(url)
            self._current_url = copy.deepcopy(url)
            self._temp_url = None

        # Maintain name of podcast.
        if name is None or name == "":
            raise E.MalformedSubscriptionError("No name provided.")
        else:
            LOGGER.debug("Provided name '%s'.", name)
            self.name = name

        # Our file downloader.
        self.downloader = Util.generate_downloader(HEADERS, self.name)

        # Use etag and last-modified to detect when we have the latest feed.
        self.etag = None
        self.last_modified = None
        self.feed_state = _FeedState()

        self.directory = None
        self._handle_directory(directory)

        self.download_backlog = download_backlog
        LOGGER.debug("Set to download backlog: %s.", download_backlog)

        self.backlog_limit = backlog_limit

        feedparser.USER_AGENT = CONSTANTS.USER_AGENT

    @classmethod
    def decode_subscription(cls, sub_dictionary):
        """Decode subscription from dictionary."""
        sub = Subscription.__new__(Subscription)

        # pylint: disable=protected-access
        sub._current_url = sub_dictionary["_current_url"]
        sub._provided_url = sub_dictionary["_provided_url"]
        sub.backlog_limit = sub_dictionary["backlog_limit"]
        sub.directory = sub_dictionary["directory"]
        sub.download_backlog = sub_dictionary["download_backlog"]
        sub.feed_state = _FeedState(feedparser_dict=sub_dictionary["feed_state"])
        sub.name = sub_dictionary["name"]

        # Generate data members that shouldn't/won't be cached.
        sub.downloader = Util.generate_downloader(HEADERS, sub.name)

        return sub

    @classmethod
    def encode_subscription(cls, sub):
        """Encode subscription to dictionary."""

        # pylint: disable=protected-access
        return {"__type__": "subscription",
                "__version__": CONSTANTS.VERSION,
                "_current_url": sub._current_url,
                "_provided_url": sub._provided_url,
                "backlog_limit": sub.backlog_limit,
                "directory": sub.directory,
                "download_backlog": sub.download_backlog,
                "feed_state": {"entries": sub.feed_state.entries,
                               "feed": sub.feed_state.feed,
                               "latest_entry_number": sub.feed_state.latest_entry_number,
                               "last_modified": sub.feed_state.last_modified,
                               "etag": sub.feed_state.etag},
                "name": sub.name}

    @staticmethod
    def parse_from_user_yaml(sub_yaml):
        """Parse YAML user-provided subscription into a subscription object."""

        name = sub_yaml.get("name", "Generic Podcast")

        if sub_yaml.get("url", None) is None:
            raise E.InvalidConfigError("No URL provided, URL is mandatory!")
        else:
            url = sub_yaml["url"]

        download_backlog = sub_yaml.get("download_backlog", False)
        backlog_limit = sub_yaml.get("backlog_limit", None)
        directory = sub_yaml.get("directory", None)

        return Subscription(name=name, url=url, download_backlog=download_backlog,
                            backlog_limit=backlog_limit, directory=directory)

    # "Public" functions.
    def attempt_update(self):
        """Attempt to download new entries for a subscription."""

        # Attempt to populate self.feed_state from subscription URL.
        feed_get_result = self.get_feed()
        if feed_get_result != UpdateResult.SUCCESS:
            return feed_get_result

        LOGGER.info("Subscription %s got updated feed.", self.name)

        # Only consider backlog if we don't have a latest entry number already.
        number_feeds = len(self.feed_state.entries)
        if self.feed_state.latest_entry_number is None:
            if self.download_backlog:
                if self.backlog_limit is None or self.backlog_limit == 0:
                    self.feed_state.latest_entry_number = 0
                    LOGGER.info(textwrap.dedent(
                        """\
                        Interpreting 'None' backlog limit as "No Limit" and downloading full
                        backlog ({1} entries).\
                        """.format(self.name, number_feeds)))

                elif self.backlog_limit < 0:
                    LOGGER.error("Invalid backlog limit %s, downloading nothing.",
                                 self.backlog_limit)
                    return False

                else:
                    LOGGER.info("Backlog limit is '%s'", self.backlog_limit)
                    self.backlog_limit = Util.max_clamp(self.backlog_limit, number_feeds)
                    LOGGER.info("Backlog limit clamped to '%s'", self.backlog_limit)
                    self.feed_state.latest_entry_number = number_feeds - self.backlog_limit

            else:
                self.feed_state.latest_entry_number = number_feeds
                LOGGER.info(textwrap.dedent(
                    """\
                    Download backlog for {0} is not set.
                    Downloading nothing, but setting number downloaded to {1}.\
                    """.format(self.name, self.feed_state.latest_entry_number)))

        if self.feed_state.latest_entry_number >= number_feeds:
            LOGGER.info("Number downloaded for %s matches feed entry count %s. Nothing to do.",
                        self.name, number_feeds)
            return True

        number_to_download = number_feeds - self.feed_state.latest_entry_number
        LOGGER.info(textwrap.dedent(
            """\
            Number of downloaded feeds for {0} is {1}, {2} less than feed entry count {3}.
            Downloading {2} entries.\
            """.format(self.name, self.feed_state.latest_entry_number, number_to_download,
                       number_feeds)))

        self.download_entry_files(oldest_entry_age=number_to_download-1)

        return True

    def download_entry_files(self, oldest_entry_age=-1):
        """
        Download feed enclosure(s) for all entries newer than the given oldest entry age to object
        directory.
        """

        # Downloading feeds oldest first makes the most sense for RSS feeds (IMO), so we do that.
        for entry_age in range(oldest_entry_age, -1, -1):
            LOGGER.info("Downloading entry %s for '%s'.", entry_age, self.name)

            entry = self.feed_state.entries[entry_age]
            enclosures = entry.enclosures
            num_entry_files = len(enclosures)
            LOGGER.info("There are %s files for entry with age %s.", num_entry_files, entry_age)

            # Create directory just for enclosures for this entry if there are many.
            directory = self.directory
            if num_entry_files > 1:
                directory = os.path.join(directory, entry.title)
                LOGGER.debug("Creating directory to store %s enclosures.", num_entry_files)

            for i, enclosure in enumerate(enclosures):
                LOGGER.info("Handling enclosure %s of %s.", i+1, num_entry_files)

                url = enclosure.href
                LOGGER.info("Extracted url %s.", url)

                filename = url.split('/')[-1]
                dest = os.path.join(directory, filename)
                self.downloader(url=url, dest=dest, overwrite=False)

            self.feed_state.latest_entry_number += 1
            LOGGER.info("Have downloaded %s entries for sub %s.",
                        self.feed_state.latest_entry_number, self.name)

    def update_directory(self, directory, config_dir):
        """Update directory for this subscription if a new one is provided."""
        if directory is None or directory == "":
            raise E.InvalidConfigError(desc=textwrap.dedent(
                """\
                Provided invalid sub directory '{0}' for '{1}'.\
                """.format(directory, self.name)))

        if self.directory != directory:
            if os.path.isabs(directory):
                self.directory = directory

            else:
                self.directory = os.path.join(config_dir, directory)

        if not os.path.isdir(self.directory):
            LOGGER.debug("Directory %s does not exist, creating it.", directory)
            os.makedirs(self.directory)

    def update_url(self, url):
        """Update url for this subscription if a new one is provided."""
        if url != self._provided_url:
            self._provided_url = copy.deepcopy(url)

        self._current_url = copy.deepcopy(url)

    # "Private" functions (messy internals).
    def _handle_directory(self, directory):
        """Assign directory if none was given, and create directory if necessary."""
        if directory is None:
            self.directory = CONSTANTS.APPDIRS.user_data_dir
            LOGGER.debug("No directory provided, defaulting to %s.", self.directory)
            return

        self.directory = directory
        LOGGER.debug("Provided directory %s.", directory)

        if not os.path.isdir(self.directory):
            LOGGER.debug("Directory %s does not exist, creating it.", directory)
            os.makedirs(self.directory)

    def get_feed(self, attempt_count=0):
        """Get RSS structure for this subscription. Return status code indicating result."""

        # Provide rate limiting.
        @Util.rate_limited(self._current_url, 120, self.name)
        def _helper():
            if attempt_count > MAX_RECURSIVE_ATTEMPTS:
                LOGGER.error("Too many recursive attempts (%s) to get feed for sub %s, canceling.",
                             attempt_count, self.name)
                return UpdateResult.FAILURE

            if self._current_url is None or self._current_url == "":
                LOGGER.error("URL is empty , cannot get feed for sub %s.", self.name)
                return UpdateResult.FAILURE

            LOGGER.info("Getting entries (attempt %s) for subscription %s with URL %s.",
                        attempt_count, self.name, self._current_url)

            (parsed, code) = self._feedparser_parse_with_options()
            if code != UpdateResult.SUCCESS:
                LOGGER.error("Feedparser parse failed (%s), aborting.", code)
                return code

            LOGGER.info("Feedparser parse succeeded.")

            # Detect some kinds of HTTP status codes signaling failure.
            code = self._handle_http_codes(parsed)
            if code == UpdateResult.ATTEMPT_AGAIN:
                LOGGER.warning("Transient HTTP error, attempting again.")
                temp = self._temp_url
                new_result = self.get_feed(attempt_count=attempt_count+1)
                if temp is not None:
                    self._current_url = temp

                return new_result

            elif code != UpdateResult.SUCCESS:
                LOGGER.error("Ran into HTTP error (%s), aborting.", code)
                return code

            self.feed_state = _FeedState(feedparser_dict=parsed)
            return UpdateResult.SUCCESS

        result = _helper()

        return result

    def _feedparser_parse_with_options(self):
        """
        Perform a feedparser parse, providing arguments (like etag) we might want it to use.
        Don't provide etag/last_modified if the last get was unsuccessful.
        """
        if self.feed_state.entries == [] or\
           (self.feed_state.etag is None and self.feed_state.last_modified is None):
            parsed = feedparser.parse(self._current_url)

        else:
            parsed = feedparser.parse(self._current_url, etag=self.feed_state.etag,
                                      modified=self.feed_state.last_modified)

        if "etag" in parsed:
            self.feed_state.etag = parsed["etag"]

        if "modified" in parsed:
            self.feed_state.last_modified = parsed["modified"]

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # Feedparser documentation indicates that you can always call getMessage, but it's
            # possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            LOGGER.error("Received bozo exception %s. Unable to retrieve feed with URL %s for %s.",
                         msg, self._current_url, self.name)
            result = (None, UpdateResult.FAILURE)

        elif parsed.get("status") == requests.codes["NOT_MODIFIED"]:
            LOGGER.debug("No update to feed, nothing to do.")
            result = (None, UpdateResult.UNNEEDED)

        else:
            result = (parsed, UpdateResult.SUCCESS)

        return result

    def _handle_http_codes(self, parsed):
        """
        Given feedparser parse result, determine if parse succeeded, and what to do about that.
        """
        # Feedparser gives no status if you feedparse a local file.
        if "status" not in parsed:
            LOGGER.info("Saw status 200 - OK, all is well.")
            return UpdateResult.SUCCESS

        status = parsed.get("status", 200)
        if status == requests.codes["NOT_FOUND"]:
            LOGGER.error(textwrap.dedent(
                """\
                Saw status {0}, unable to retrieve feed text for {2}.
                Current URL {1} for {2} will be preserved and checked again on next attempt.\
                """.format(status, self._current_url, self.name)))
            return UpdateResult.FAILURE

        elif status in [requests.codes["UNAUTHORIZED"], requests.codes["GONE"]]:
            LOGGER.error(textwrap.dedent(
                """\
                Saw status {0}, unable to retrieve feed text for {2}.
                Clearing stored URL {0} from _current_url for {2}.
                Originally provided URL {1} will be maintained at _provided_url, but will no longer
                be used.
                Please provide new URL and authorization for subscription {2}.\
                """.format(status, self._current_url, self.name)))

            self._current_url = None
            return UpdateResult.FAILURE

        # Handle redirecting errors
        elif status in [requests.codes["MOVED_PERMANENTLY"], requests.codes["PERMANENT_REDIRECT"]]:
            LOGGER.warning(textwrap.dedent(
                """\
                Saw status {0} indicating permanent URL change.
                Changing stored URL {1} for {2} to {3} and attempting get with new URL.\
                """.format(status, self._current_url, self.name, parsed.href)))

            self._current_url = parsed.href
            return UpdateResult.ATTEMPT_AGAIN

        elif status in [requests.codes["FOUND"], requests.codes["SEE_OTHER"],
                        requests.codes["TEMPORARY_REDIRECT"]]:
            LOGGER.warning(textwrap.dedent(
                """\
                Saw status {0} indicating temporary URL change.
                Attempting with new URL {1}. Stored URL {2} for {3} will be unchanged.\
                """.format(status, parsed.href, self._current_url, self.name)))

            self._temp_url = self._current_url
            self._current_url = parsed.href
            return UpdateResult.ATTEMPT_AGAIN

        elif status != 200:
            LOGGER.warning("Saw status %s. Attempting retrieve with URL %s for %s again.",
                           status, self._current_url, self.name)
            return UpdateResult.ATTEMPT_AGAIN

        else:
            LOGGER.info("Saw status 200. Sucess!")
            return UpdateResult.SUCCESS

    def __eq__(self, rhs):
        return isinstance(rhs, Subscription) and repr(self) == repr(rhs)

    def __ne__(self, rhs):
        return not self.__eq__(rhs)

    def __repr__(self):
        return str(Subscription.encode_subscription(self))


# pylint: disable=too-few-public-methods
class _FeedState(object):
    def __init__(self, feedparser_dict=None):
        if feedparser_dict is not None:
            self.feed = feedparser_dict.get("feed", {})
            self.entries = feedparser_dict.get("entries", [])
            self.last_modified = feedparser_dict.get("last_modified", None)
            self.etag = feedparser_dict.get("etag", None)
            self.latest_entry_number = feedparser_dict.get("latest_entry_number", None)
        else:
            self.feed = {}
            self.entries = []
            self.last_modified = None
            self.etag = None
            self.latest_entry_number = None


# pylint: disable=too-few-public-methods
class UpdateResult(Enum):
    """Enum describing possible results of trying to update a subscription."""
    SUCCESS = 0
    UNNEEDED = -1
    FAILURE = -2
    ATTEMPT_AGAIN = -3
