"""
Module for a subscription object, which manages a podcast URL, name, and information about how
many episodes of the podcast we have.
"""
import copy
import logging
import os
import platform
import textwrap
import time
from datetime import datetime
from enum import Enum
from time import mktime

import feedparser
import requests

import puckfetcher.constants as CONSTANTS
import puckfetcher.error as E
import puckfetcher.util as Util

DATE_FORMAT_STRING = "%Y%m%dT%H:%M:%S.%f"
HEADERS = {"User-Agent": CONSTANTS.USER_AGENT}
MAX_RECURSIVE_ATTEMPTS = 10

LOG = logging.getLogger("root")


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
            LOG.debug("Storing provided url '%s'.", url)
            self._provided_url = copy.deepcopy(url)
            self._current_url = copy.deepcopy(url)
            self._temp_url = None

        # Maintain name of podcast.
        if name is None or name == "":
            raise E.MalformedSubscriptionError("No name provided.")
        else:
            LOG.debug("Provided name '%s'.", name)
            self.name = name

        # Our file downloader.
        self.downloader = Util.generate_downloader(HEADERS, self.name)

        # Store feed state, including etag/last_modified.
        self.feed_state = _FeedState()

        self.directory = None
        self._handle_directory(directory)

        self.download_backlog = download_backlog
        LOG.debug("Set to download backlog: %s.", download_backlog)

        self.backlog_limit = backlog_limit

        feedparser.USER_AGENT = CONSTANTS.USER_AGENT

    # TODO find out what passing None to msgpack will do, and if that's reasonable.
    @classmethod
    def decode_subscription(cls, sub_dictionary):
        """Decode subscription from dictionary."""
        sub = Subscription.__new__(Subscription)

        attrs = ["name", "_current_url", "_provided_url"]

        for attr in attrs:
            if attr not in sub_dictionary.keys():
                logger.error("Sub to decode is missing %s, can't continue.", attr)
                return None
            else:
                setattr(sub, attr, sub_dictionary[attr])

        sub.directory = sub_dictionary.get("directory", None)
        sub.download_backlog = sub_dictionary.get("download_backlog", None)
        sub.backlog_limit = sub_dictionary.get("backlog_limit", None)
        sub.use_title_as_filename = sub_dictionary.get("use_title_as_filename", None)
        sub.feed_state = _FeedState(feedparser_dict=sub_dictionary.get("feed_state", None))

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
                "directory": sub.directory,
                "download_backlog": sub.download_backlog,
                "backlog_limit": sub.backlog_limit,
                "use_title_as_filename": sub.use_title_as_filename,
                "feed_state": sub.feed_state.as_dict(),
                "name": sub.name}

    @staticmethod
    def parse_from_user_yaml(sub_yaml, defaults):
        """
        Parse YAML user-provided subscription into a subscription object, using config-provided
        options as defaults.
        Return None instead of a subscription if we were not able to parse something.
        """

        sub = Subscription.__new__(Subscription)

        if "name" not in sub_yaml.keys():
            logger.error("No name provided, name is mandatory!")
            return None
        else:
            sub.name = sub_yaml["name"]

        if "url" not in sub_yaml.keys():
            logger.error("No URL provided, URL is mandatory!")
            return None
        else:
            sub.url = sub_yaml["url"]

        sub.directory = sub_yaml.get("directory", os.path.join(defaults["directory"], sub.name))
        sub.download_backlog = sub_yaml.get("download_backlog", defaults["download_backlog"])
        sub.backlog_limit = sub_yaml.get("backlog_limit", defaults["backlog_limit"])
        sub.use_title_as_filename = sub_yaml.get("use_title_as_filename",
                                                 defaults["use_title_as_filename"])

        return sub

    # "Public" functions.
    def attempt_update(self):
        """Attempt to download new entries for a subscription."""

        # Attempt to populate self.feed_state from subscription URL.
        feed_get_result = self.get_feed()
        if feed_get_result != UpdateResult.SUCCESS:
            return feed_get_result

        LOG.info("Subscription {0} got updated feed.", self.name)

        # Only consider backlog if we don't have a latest entry number already.
        number_feeds = len(self.feed_state.entries)
        if self.feed_state.latest_entry_number is None:
            if self.download_backlog:
                if self.backlog_limit is None or self.backlog_limit == 0:
                    self.feed_state.latest_entry_number = 0
                    LOG.info(textwrap.dedent(
                        """\
                        Interpreting 'None' backlog limit as "No Limit" and downloading full
                        backlog ({0} entries).\
                        """.format(number_feeds)))

                elif self.backlog_limit < 0:
                    LOG.error("Invalid backlog limit %s, downloading nothing.", self.backlog_limit)
                    return False

                else:
                    LOG.info("Backlog limit is '%s'", self.backlog_limit)
                    self.backlog_limit = Util.max_clamp(self.backlog_limit, number_feeds)
                    LOG.info("Backlog limit clamped to '%s'", self.backlog_limit)
                    self.feed_state.latest_entry_number = number_feeds - self.backlog_limit

            else:
                self.feed_state.latest_entry_number = number_feeds
                LOG.info(textwrap.dedent(
                    """\
                    Download backlog for {0} is not set.
                    Downloading nothing, but setting number downloaded to {1}.\
                    """.format(self.name, self.feed_state.latest_entry_number)))

        if self.feed_state.latest_entry_number >= number_feeds:
            LOG.info("Number downloaded for %s matches feed entry count %s. Nothing to do.",
                        self.name, number_feeds)
            return True

        number_to_download = number_feeds - self.feed_state.latest_entry_number
        LOG.info(textwrap.dedent(
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
            LOG.info("Downloading entry %s for '%s'.", entry_age, self.name)

            entry = self.feed_state.entries[entry_age]
            enclosures = entry.enclosures
            num_entry_files = len(enclosures)
            LOG.info("There are %s files for entry with age %s.", num_entry_files, entry_age)

            # Create directory just for enclosures for this entry if there are many.
            directory = self.directory
            if num_entry_files > 1:
                directory = os.path.join(directory, entry.title)
                LOG.debug("Creating directory to store %s enclosures.", num_entry_files)

            for i, enclosure in enumerate(enclosures):
                LOG.info("Handling enclosure %s of %s.", i+1, num_entry_files)

                url = enclosure.href
                LOG.info("Extracted url %s.", url)

                # Update filename if we're supposed to.
                url_filename = url.split("/")[-1]

                # TODO do some bullshit to make this a windows-safe filename.
                if platform.system() == 'Windows':
                    logger.error(textwrap.dedent(
                        """\
                        Sorry, we can't guarantee valid filenames on Windows if we use RSS
                        subscription titles.
                        We'll support it eventually!
                        Using URL filename for now.\
                        """))
                    filename = url_filename

                elif self.use_title_as_filename:
                    ext = os.path.splitext(url_filename)[1]
                    filename = "{}{}".format(entry.title, ext) # It's an owl!

                else:
                    filename = url_filename

                # Remove characters we can't allow in filenames.
                filename = Util.sanitize(filename)

                dest = os.path.join(directory, filename)

                # TODO catch errors? What if we try to save to a nonsense file?
                self.downloader(url=url, dest=dest, overwrite=False)

            self.feed_state.latest_entry_number += 1
            LOG.info("Have downloaded %s entries for sub %s.",
                     self.feed_state.latest_entry_number, self.name)

    def update_directory(self, directory, config_dir):
        """Update directory for this subscription if a new one is provided."""
        if directory is None or directory == "":
            raise E.InvalidConfigError(desc=textwrap.dedent(
                """\
                Provided invalid sub directory '{}' for '{}'.\
                """.format(directory, self.name)))

        directory = Util.expand(directory)

        if self.directory != directory:
            if os.path.isabs(directory):
                self.directory = directory

            else:
                self.directory = os.path.join(config_dir, directory)

            if not os.path.isdir(self.directory):
                LOG.debug("Directory %s does not exist, creating it.", directory)
                os.makedirs(self.directory)

    def update_url(self, url):
        """Update url for this subscription if a new one is provided."""
        if hasattr(self, "_provided_url"):
            if url != self._provided_url:
                self._provided_url = copy.deepcopy(url)

        else:
            self._provided_url = copy.deepcopy(url)

        self._current_url = copy.deepcopy(url)

    # TODO clean this up - reflection, or whatever Python has for that?
    def default_missing_fields(self, settings):
        """Set default values for any fields that are None (ones that were never set."""

        # NOTE - directory is set separately, because we'll want to create it.
        # These are just plain options.

        if self.download_backlog is None:
            self.download_backlog = settings["download_backlog"]

        if self.backlog_limit is None:
            self.backlog_limit = settings["backlog_limit"]

        if self.use_title_as_filename is None:
            self.use_title_as_filename = settings["use_title_as_filename"]

        if not hasattr(self, "feed_state") or self.feed_state is None:
            self.feed_state = _FeedState()

        self.downloader = Util.generate_downloader(HEADERS, self.name)

    def get_status(self, index, total_subs):
        """Provide status of subscription, as a multiline string"""
        lines = []

        pad_num = len(str(total_subs))
        padded_cur_num = str(index).zfill(pad_num)
        header = "Sub number %s/%s - '%s' |%s|".format(padded_cur_num, total_subs, self.name,
                                                         self.feed_state.latest_entry_number)
        lines.append(header)
        return "".join(lines)

    # "Private" functions (messy internals).
    def _handle_directory(self, directory):
        """Assign directory if none was given, and create directory if necessary."""
        directory = Util.expand(directory)
        if directory is None:
            self.directory = Util.expand(CONSTANTS.APPDIRS.user_data_dir)
            LOG.debug("No directory provided, defaulting to %s.", self.directory)
            return

        self.directory = directory
        LOG.debug("Provided directory %s.", directory)

        if not os.path.isdir(self.directory):
            LOG.debug("Directory %s does not exist, creating it.", directory)
            os.makedirs(self.directory)

    def get_feed(self, attempt_count=0):
        """Get RSS structure for this subscription. Return status code indicating result."""

        # Provide rate limiting.
        @Util.rate_limited(self._current_url, 120, self.name)
        def _helper():
            if attempt_count > MAX_RECURSIVE_ATTEMPTS:
                LOG.error("Too many recursive attempts (%s) to get feed for sub %s, canceling.",
                             attempt_count, self.name)
                return UpdateResult.FAILURE

            if self._current_url is None or self._current_url == "":
                LOG.error("URL is empty , cannot get feed for sub %s.", self.name)
                return UpdateResult.FAILURE

            LOG.info("Getting entries (attempt %s) for subscription %s with URL %s.",
                        attempt_count, self.name, self._current_url)

            (parsed, code) = self._feedparser_parse_with_options()
            if code == UpdateResult.UNNEEDED:
                LOG.info("We have the latest feed, nothing to do.")
                return code

            elif code != UpdateResult.SUCCESS:
                LOG.error("Feedparser parse failed (%s), aborting.", code)
                return code

            LOG.info("Feedparser parse succeeded.")

            # Detect some kinds of HTTP status codes signaling failure.
            code = self._handle_http_codes(parsed)
            if code == UpdateResult.ATTEMPT_AGAIN:
                LOG.warning("Transient HTTP error, attempting again.")
                temp = self._temp_url
                new_result = self.get_feed(attempt_count=attempt_count+1)
                if temp is not None:
                    self._current_url = temp

                return new_result

            elif code != UpdateResult.SUCCESS:
                LOG.error("Ran into HTTP error (%s), aborting.", code)
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
        if (not self.feed_state.has_state) or (self.feed_state.last_modified is None and \
                                           self.feed_state.etag is None):
            parsed = feedparser.parse(self._current_url)

        elif self.feed_state.last_modified is not None and self.feed_state.etag is not None:
            time_struct = self.feed_state.last_modified.timetuple()
            parsed = feedparser.parse(self._current_url, etag=self.feed_state.etag,
                                      modified=time_struct)

        elif self.feed_state.last_modified is not None:
            time_struct = self.feed_state.last_modified.timetuple()
            parsed = feedparser.parse(self._current_url, modified=time_struct)

        else:
            parsed = feedparser.parse(self._current_url, etag=self.feed_state.etag)

        self.feed_state.etag = parsed.get("etag", self.feed_state.etag)
        self.feed_state.store_last_modified(parsed.get("modified_parsed",
                                            self.feed_state.last_modified))

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # Feedparser documentation indicates that you can always call getMessage, but it's
            # possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            LOG.error("Received bozo exception %s. Unable to retrieve feed with URL %s for %s.",
                         msg, self._current_url, self.name)
            return (None, UpdateResult.FAILURE)

        elif parsed.get("status") == requests.codes["NOT_MODIFIED"]:
            LOG.debug("No update to feed, nothing to do.")
            return (None, UpdateResult.UNNEEDED)

        else:
            return (parsed, UpdateResult.SUCCESS)

    def _handle_http_codes(self, parsed):
        """
        Given feedparser parse result, determine if parse succeeded, and what to do about that.
        """
        # Feedparser gives no status if you feedparse a local file.
        if "status" not in parsed:
            LOG.info("Saw status 200 - OK, all is well.")
            return UpdateResult.SUCCESS

        status = parsed.get("status", 200)
        if status == requests.codes["NOT_FOUND"]:
            LOG.error(textwrap.dedent(
                """\
                Saw status {0}, unable to retrieve feed text for {2}.
                Current URL {1} for {2} will be preserved and checked again on next attempt.\
                """.format(status, self._current_url, self.name)))
            return UpdateResult.FAILURE

        elif status in [requests.codes["UNAUTHORIZED"], requests.codes["GONE"]]:
            LOG.error(textwrap.dedent(
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
            LOG.warning(textwrap.dedent(
                """\
                Saw status {} indicating permanent URL change.
                Changing stored URL {} for {} to {} and attempting get with new URL.\
                """.format(status, self._current_url, self.name, parsed.href)))

            self._current_url = parsed.href
            return UpdateResult.ATTEMPT_AGAIN

        elif status in [requests.codes["FOUND"], requests.codes["SEE_OTHER"],
                        requests.codes["TEMPORARY_REDIRECT"]]:
            LOG.warning(textwrap.dedent(
                """\
                Saw status %s indicating temporary URL change.
                Attempting with new URL %s. Stored URL %s for %s will be unchanged.\
                """.format(status, parsed.href, self._current_url, self.name)))

            self._temp_url = self._current_url
            self._current_url = parsed.href
            return UpdateResult.ATTEMPT_AGAIN

        elif status != 200:
            LOG.warning("Saw status %s. Attempting retrieve with URL %s for %s again.",
                           status, self._current_url, self.name)
            return UpdateResult.ATTEMPT_AGAIN

        else:
            LOG.info("Saw status 200. Sucess!")
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

            # NOTE: This should be deprecated eventually.
            temp_date = feedparser_dict.get("last_modified", None)
            if type(temp_date) is time.struct_time:
                temp_date = datetime.fromtimestamp(mktime(struct))
            elif type(temp_date) is datetime:
                temp_date = datetime.strptime(obj["as_str"], DATE_FORMAT_STRING)
            self.last_modified = temp_date

            self.etag = feedparser_dict.get("etag", None)
            self.latest_entry_number = feedparser_dict.get("latest_entry_number", None)
            self.has_state = True

        else:
            self.feed = {}
            self.entries = []
            self.last_modified = None
            self.etag = None
            self.latest_entry_number = None
            self.has_state = False

    def as_dict(self):
        """Return dictionary of this feed state object."""

        if self.last_modified is not None:
            store_date = self.last_modified.strftime(DATE_FORMAT_STRING)
        else:
            store_date = None
        return {"entries": self.entries,
                "feed": self.feed,
                "latest_entry_number": self.latest_entry_number,
                "last_modified": store_date,
                "etag": self.etag}

    def store_last_modified(self, last_modified):
        """Store last_modified as a datetime, regardless of form it's provided in."""
        if type(last_modified) is time.struct_time:
            self.last_modified = datetime.fromtimestamp(mktime(last_modified))
        elif type(last_modified) is datetime:
            self.last_modified = last_modified
        elif type(last_modified) is type(None):
            LOG.info("last_modified is None, ignoring.")
        else:
            LOG.warning("Unhandled type, ignoring.")


# pylint: disable=too-few-public-methods
class UpdateResult(Enum):
    """Enum describing possible results of trying to update a subscription."""
    SUCCESS = 0
    UNNEEDED = -1
    FAILURE = -2
    ATTEMPT_AGAIN = -3
