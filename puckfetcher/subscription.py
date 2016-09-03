"""
Module for a subscription object, which manages a podcast URL, name, and information about how
many episodes of the podcast we have.
"""

import logging
import os
import platform
import textwrap
import time
from time import mktime
from collections import deque
from datetime import datetime
from enum import Enum

import feedparser
import requests

import puckfetcher.constants as CONSTANTS
import puckfetcher.error as ERROR
import puckfetcher.util as Util

try:
    xrange
except NameError:
    # pylint: disable=invalid-name
    xrange = range

DATE_FORMAT_STRING = "%Y%m%dT%H:%M:%S.%f"
HEADERS = {"User-Agent": CONSTANTS.USER_AGENT}
MAX_RECURSIVE_ATTEMPTS = 10

LOG = logging.getLogger("root")


# TODO describe field members, function parameters in docstrings.
class Subscription(object):
    """Object describing a podcast subscription."""

    def __init__(self, url=None, name=None, directory=None, backlog_limit=0):

        self.temp_url = None

        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if url is None or url == "":
            raise ERROR.MalformedSubscriptionError("No URL provided.")
        else:
            LOG.debug("Storing provided url '%s'.", url)
            self.url = url
            self.original_url = url

        # Maintain name of podcast.
        if name is None or name == "":
            raise ERROR.MalformedSubscriptionError("No name provided.")
        else:
            LOG.debug("Provided name '%s'.", name)
            self.name = name

        # Our file downloader.
        self.downloader = Util.generate_downloader(HEADERS, self.name)

        # Store feed state, including etag/last_modified.
        self.feed_state = _FeedState()

        self.directory = _process_directory(directory)

        self.backlog_limit = backlog_limit

        self.use_title_as_filename = None

        feedparser.USER_AGENT = CONSTANTS.USER_AGENT

    # TODO find out what passing None to msgpack will do, and if that's reasonable.
    @classmethod
    def decode_subscription(cls, sub_dictionary):
        """Decode subscription from dictionary."""
        sub = Subscription.__new__(Subscription)

        attrs = ["name", "original_url", "url"]

        for attr in attrs:
            if attr not in sub_dictionary.keys():
                LOG.error("Sub to decode is missing %s, can't continue.", attr)
                return None
            else:
                setattr(sub, attr, sub_dictionary[attr])

        sub.directory = sub_dictionary.get("directory", None)

        # NOTE - Deprecate eventually.
        if "download_backlog" in sub_dictionary.keys():
            if sub_dictionary["download_backlog"]:
                sub.backlog_limit = sub_dictionary["backlog_limit"]
            else:
                sub.backlog_limit = 0

        # NOTE - deprecate eventually.
        if "_current_url" in sub_dictionary.keys():
            sub.url = sub_dictionary["_current_url"]

        # NOTE - deprecate eventually.
        if "_provided_url" in sub_dictionary.keys():
            sub.original_url = sub_dictionary["_provided_url"]

        sub.backlog_limit = sub_dictionary.get("backlog_limit", 0)
        sub.use_title_as_filename = sub_dictionary.get("use_title_as_filename", None)
        sub.feed_state = _FeedState(feedstate_dict=sub_dictionary.get("feed_state", None))

        # Generate data members that shouldn't/won't be cached.
        sub.downloader = Util.generate_downloader(HEADERS, sub.name)

        return sub

    @classmethod
    def encode_subscription(cls, sub):
        """Encode subscription to dictionary."""

        return {"__type__": "subscription",
                "__version__": CONSTANTS.VERSION,
                "url": sub.url,
                "original_url": sub.original_url,
                "directory": sub.directory,
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
            LOG.error("No name provided, name is mandatory!")
            return None

        if "url" not in sub_yaml.keys():
            LOG.error("No URL provided, URL is mandatory!")
            return None

        sub.name = sub_yaml["name"]
        sub.url = sub_yaml["url"]
        sub.original_url = sub_yaml["url"]
        sub.directory = sub_yaml.get("directory", os.path.join(defaults["directory"], sub.name))
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

        LOG.info("Subscription %s got updated feed.", self.name)

        # Only consider backlog if we don't have a latest entry number already.
        number_feeds = len(self.feed_state.entries)
        if self.feed_state.latest_entry_number is None:
            if self.backlog_limit is None:
                self.feed_state.latest_entry_number = 0
                LOG.info(
                    textwrap.dedent(
                        """\
                        Interpreting 'None' backlog limit as "No Limit" and downloading full
                        backlog (%s entries).\
                        """),
                    number_feeds)

            elif self.backlog_limit < 0:
                LOG.error("Invalid backlog limit %s, downloading nothing.", self.backlog_limit)
                return False

            elif self.backlog_limit > 0:
                LOG.info("Backlog limit provided as '%s'", self.backlog_limit)
                self.backlog_limit = Util.max_clamp(self.backlog_limit, number_feeds)
                LOG.info("Backlog limit clamped to '%s'", self.backlog_limit)
                self.feed_state.latest_entry_number = number_feeds - self.backlog_limit

            else:
                self.feed_state.latest_entry_number = number_feeds
                LOG.info(
                    textwrap.dedent(
                        """\
                        Download backlog for %s is zero.
                        Not downloading backlog but setting number downloaded to %s.\
                        """),
                    self.name, self.feed_state.latest_entry_number)

        if self.feed_state.latest_entry_number >= number_feeds:
            LOG.info("Number downloaded for %s matches feed entry count %s. Nothing to do.",
                     self.name, number_feeds)
            return True

        number_to_download = number_feeds - self.feed_state.latest_entry_number
        LOG.info(
            textwrap.dedent(
                """\
                Number of downloaded feeds for %s is %s, %s less than feed entry count %s.
                Downloading %s entries.\
                """),
            self.name, self.feed_state.latest_entry_number, number_to_download, number_feeds,
            number_to_download)

        # Queuing feeds in order of age makes the most sense for RSS feeds (IMO), so we do that.
        # TODO consider wrapping queue more.
        age_range = xrange(self.feed_state.latest_entry_number, number_feeds)
        for i in age_range:
            self.feed_state.queue.append((i+1, False))
        self.download_queue()

        return True

    def download_queue(self):
        """
        Download feed enclosure(s) for all entries in the queue.
        Map from positive indexing we use in the queue to negative feed age indexing used in feed.
        """

        msg = "Queue for sub {} has {} entries.".format(self.name, len(self.feed_state.queue))
        LOG.info(msg)
        print(msg)

        try:
            while self.feed_state.queue:
                (entry_num, overwrite) = self.feed_state.queue.popleft()
                entry_num = entry_num - 1
                num_entries = len(self.feed_state.entries)
                entry_age = num_entries - (entry_num + 1)

                entry = self.feed_state.entries[entry_age]

                urls = entry["urls"]
                num_entry_files = len(urls)

                msg = "Trying to download entry number {} (age {}) for '{}'.".format(entry_num,
                                                                                     entry_age,
                                                                                     self.name)
                LOG.info(msg)
                print(msg)

                # Create directory just for enclosures for this entry if there are many.
                directory = self.directory
                if num_entry_files > 1:
                    directory = os.path.join(directory, entry["title"])
                    LOG.info("Creating directory to store %s enclosures.", num_entry_files)
                    print("{} enclosures for this feed entry.".format(num_entry_files))

                for i, url in enumerate(urls):
                    if num_entry_files > 1:
                        LOG.info("Handling enclosure %s of %s.", i+1, num_entry_files)
                        print("Downloading enclosure {} of {}".format(i+1, num_entry_files))

                    LOG.info("Extracted url %s.", url)

                    # TODO catch errors? What if we try to save to a nonsense file?
                    dest = self._get_dest(url, entry["title"], directory)
                    self.downloader(url=url, dest=dest, overwrite=overwrite)

                if entry_num > self.feed_state.latest_entry_number:
                    self.feed_state.latest_entry_number = entry_num

                self.feed_state.entries_state_dict[entry_num] = True
                LOG.info("Have downloaded %s entries for sub %s.",
                         self.feed_state.latest_entry_number, self.name)

        except KeyboardInterrupt:
            self.feed_state.queue.appendleft((entry_num, True))

    def enqueue(self, nums):
        """Add entries to this subscription's download queue."""
        actual_nums = []
        for num in nums:
            if num > 0 and num <= len(self.feed_state.entries) \
               and num not in self.feed_state.queue:
                actual_nums.append((num, True))

        self.feed_state.queue.extend(actual_nums)
        LOG.info("New queue for %s: %s", self.name, list(self.feed_state.queue))

        return actual_nums

    def update(self, directory=None, config_dir=None, url=None, set_original=False, name=None):
        """Update values for this subscription."""
        if directory == "":
            raise ERROR.InvalidConfigError(desc=textwrap.dedent(
                """\
                Provided invalid sub directory '{}' for '{}'.\
                """.format(directory, self.name)))

        if directory is not None:
            directory = Util.expand(directory)

            if self.directory != directory:
                if os.path.isabs(directory):
                    self.directory = directory

                else:
                    self.directory = os.path.join(config_dir, directory)

                if not os.path.isdir(self.directory):
                    LOG.debug("Directory %s does not exist, creating it.", directory)
                    os.makedirs(self.directory)

        if url is not None:
            self.url = url

            if set_original:
                self.original_url = url

        if name is not None:
            self.name = name

    def default_missing_fields(self, settings):
        """Set default values for any fields that are None (ones that were never set)."""

        # NOTE - directory is set separately, because we'll want to create it.
        # These are just plain options.

        if self.backlog_limit is None:
            self.backlog_limit = settings["backlog_limit"]

        if self.use_title_as_filename is None:
            self.use_title_as_filename = settings["use_title_as_filename"]

        if not hasattr(self, "feed_state") or self.feed_state is None:
            self.feed_state = _FeedState()

        self.downloader = Util.generate_downloader(HEADERS, self.name)

    def get_status(self, index, total_subs):
        """Provide status of subscription."""
        pad_num = len(str(total_subs))
        padded_cur_num = str(index+1).zfill(pad_num)
        return "{}/{} - '{}' |{}|".format(padded_cur_num, total_subs, self.name,
                                          self.feed_state.latest_entry_number-1)

    def get_details(self, index, total_subs):
        """Provide multiline summary of subscription state."""
        detail_lines = []

        detail_lines.append(self.get_status(index, total_subs))

        num_entries = len(self.feed_state.entries)
        pad_num = len(str(num_entries))
        detail_lines.append("Status of podcast queue:")
        detail_lines.append("{}".format(list(self.feed_state.queue)))
        detail_lines.append("")
        detail_lines.append("Status of podcast entries:")

        entry_indicators = []
        for i in xrange(num_entries+1):
            if i in self.feed_state.entries_state_dict.keys():
                entry_indicators.append("{}+".format(str(i+1).zfill(pad_num)))
            else:
                entry_indicators.append("{}-".format(str(i+1).zfill(pad_num)))

        detail_lines.append(" ".join(entry_indicators))

        return "\n".join(detail_lines)

    def get_feed(self, attempt_count=0):
        """Get RSS structure for this subscription. Return status code indicating result."""

        @Util.rate_limited(self.url, 120, self.name)
        def _helper():
            res = None
            if attempt_count > MAX_RECURSIVE_ATTEMPTS:
                LOG.error("Too many recursive attempts (%s) to get feed for sub %s, canceling.",
                          attempt_count, self.name)
                res = UpdateResult.FAILURE

            elif self.url is None or self.url == "":
                LOG.error("URL is empty , cannot get feed for sub %s.", self.name)
                res = UpdateResult.FAILURE

            if res != None:
                return res

            else:
                LOG.info("Getting entries (attempt %s) for subscription %s with URL %s.",
                         attempt_count, self.name, self.url)

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
                temp = self.temp_url
                code = self.get_feed(attempt_count=attempt_count+1)
                if temp is not None:
                    self.url = temp

            elif code != UpdateResult.SUCCESS:
                LOG.error("Ran into HTTP error (%s), aborting.", code)

            else:
                self.feed_state.load_rss_info(parsed)

            return code

        return _helper()

    def as_config_yaml(self):
        """Return self as config file YAML."""

        return {"url": self.original_url,
                "name": self.name,
                "backlog_limit": self.backlog_limit,
                "directory": self.directory}


    # "Private" class functions (messy internals).
    def _feedparser_parse_with_options(self):
        """
        Perform a feedparser parse, providing arguments (like etag) we might want it to use.
        Don't provide etag/last_modified if the last get was unsuccessful.
        """
        if self.feed_state.last_modified is not None:
            last_mod = self.feed_state.last_modified.timetuple()
        else:
            last_mod = None

        # Not sure why pylint can't work this out.
        # pylint: disable=no-member
        parsed = feedparser.parse(self.url, etag=self.feed_state.etag, modified=last_mod)

        self.feed_state.etag = parsed.get("etag", self.feed_state.etag)
        self.feed_state.store_last_modified(
            parsed.get("modified_parsed", self.feed_state.last_modified))

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # NOTE: Feedparser documentation indicates that you can always call getMessage, but
            # it's possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            LOG.error("Received bozo exception %s. Unable to retrieve feed with URL %s for %s.",
                      msg, self.url, self.name)
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
        result = UpdateResult.SUCCESS
        if status == requests.codes["NOT_FOUND"]:
            LOG.error(
                textwrap.dedent(
                    """\
                    Saw status %s, unable to retrieve feed text for %s.
                    Stored URL %s for %s will be preserved and checked again on next attempt.\
                    """),
                status, self.name, self.url, self.name)

            # pylint: disable=redefined-variable-type
            result = UpdateResult.FAILURE

        elif status in [requests.codes["UNAUTHORIZED"], requests.codes["GONE"]]:
            LOG.error(
                textwrap.dedent(
                    """\
                    Saw status %s, unable to retrieve feed text for %s.
                    Clearing stored URL %s for %s.
                    Please provide new URL and authorization for subscription %s.\
                    """),
                status, self.name, self.url, self.name, self.name)

            self.url = None
            result = UpdateResult.FAILURE

        # Handle redirecting errors
        elif status in [requests.codes["MOVED_PERMANENTLY"], requests.codes["PERMANENT_REDIRECT"]]:
            LOG.warning(
                textwrap.dedent(
                    """\
                    Saw status %s indicating permanent URL change.
                    Changing stored URL %s for %s to %s and attempting get with new URL.\
                    """),
                status, self.url, self.name, parsed.href)

            self.url = parsed.href
            result = UpdateResult.ATTEMPT_AGAIN

        elif status in [requests.codes["FOUND"], requests.codes["SEE_OTHER"],
                        requests.codes["TEMPORARY_REDIRECT"]]:
            LOG.warning(
                textwrap.dedent(
                    """\
                    Saw status %s indicating temporary URL change.
                    Attempting with new URL %s. Stored URL %s for %s will be unchanged.\
                    """),
                status, parsed.href, self.url, self.name)

            self.temp_url = self.url
            self.url = parsed.href
            result = UpdateResult.ATTEMPT_AGAIN

        elif status != 200:
            LOG.warning("Saw status %s. Attempting retrieve with URL %s for %s again.",
                        status, self.url, self.name)
            result = UpdateResult.ATTEMPT_AGAIN

        else:
            LOG.info("Saw status 200. Success!")

        return result

    def _get_dest(self, url, title, directory):
        url_filename = url.split("/")[-1]

        if platform.system() == 'Windows':
            LOG.error(textwrap.dedent(
                """\
                Sorry, we can't guarantee valid filenames on Windows if we use RSS
                subscription titles.
                We'll support it eventually!
                Using URL filename.\
                """))
            filename = url_filename

        elif self.use_title_as_filename:
            ext = os.path.splitext(url_filename)[1][1:]
            filename = "{}.{}".format(title, ext) # It's an owl!

        else:
            filename = url_filename

        # Remove characters we can't allow in filenames.
        filename = Util.sanitize(filename)

        return os.path.join(directory, filename)

    def __eq__(self, rhs):
        return isinstance(rhs, Subscription) and repr(self) == repr(rhs)

    def __ne__(self, rhs):
        return not self.__eq__(rhs)

    def __repr__(self):
        return str(Subscription.encode_subscription(self))


class _FeedState(object):
    def __init__(self, feedstate_dict=None):
        if feedstate_dict is not None:
            LOG.info("Successfully loaded feed state dict.")

            self.feed = feedstate_dict.get("feed", {})
            self.entries = feedstate_dict.get("entries", [])
            self.entries_state_dict = feedstate_dict.get("entries_state_dict", {})
            self.queue = deque(feedstate_dict.get("queue", []))

            # NOTE: This should be deprecated eventually.
            temp_date = feedstate_dict.get("last_modified", None)
            if isinstance(temp_date, time.struct_time):
                LOG.debug("Loading type time.struct_time last_modified.")
                self.last_modified = datetime.fromtimestamp(mktime(temp_date))
            else:
                LOG.debug("Refusing to load unsupported type.")
                self.last_modified = None

            self.etag = feedstate_dict.get("etag", None)
            self.latest_entry_number = feedstate_dict.get("latest_entry_number", None)

        else:
            LOG.info("Did not successfully load feed state dict.")

            self.feed = {}
            self.entries = []
            self.entries_state_dict = {}
            self.queue = deque([])
            self.last_modified = None
            self.etag = None
            self.latest_entry_number = None

    def load_rss_info(self, parsed):
        """Load some RSS subscription elements into this feed state."""
        self.entries = []
        for entry in parsed["entries"]:
            new_entry = {}
            new_entry["title"] = entry["title"]

            new_entry["urls"] = []
            for enclosure in entry["enclosures"]:
                new_entry["urls"].append(enclosure["href"])

            self.entries.append(new_entry)

    def as_dict(self):
        """Return dictionary of this feed state object."""

        return {"entries": self.entries,
                "entries_state_dict": self.entries_state_dict,
                "queue": list(self.queue),
                "latest_entry_number": self.latest_entry_number,
                "last_modified": None,
                "etag": self.etag}

    def store_last_modified(self, last_modified):
        """Store last_modified as a datetime, regardless of form it's provided in."""
        if isinstance(last_modified, time.struct_time):
            self.last_modified = datetime.fromtimestamp(mktime(last_modified))
        elif isinstance(last_modified, datetime):
            self.last_modified = last_modified
        elif isinstance(last_modified, type(None)):
            LOG.info("last_modified is None, ignoring.")
        else:
            LOG.warning("Unhandled type, ignoring.")


# "Private" file functions (messy internals).
def _process_directory(directory):
    """Assign directory if none was given, and create directory if necessary."""
    directory = Util.expand(directory)
    if directory is None:
        LOG.debug("No directory provided, defaulting to %s.", directory)
        return Util.expand(CONSTANTS.APPDIRS.user_data_dir)

    LOG.debug("Provided directory %s.", directory)

    if not os.path.isdir(directory):
        LOG.debug("Directory %s does not exist, creating it.", directory)
        os.makedirs(directory)

    return directory


# pylint: disable=too-few-public-methods
class UpdateResult(Enum):
    """Enum describing possible results of trying to update a subscription."""
    SUCCESS = 0
    UNNEEDED = -1
    FAILURE = -2
    ATTEMPT_AGAIN = -3
