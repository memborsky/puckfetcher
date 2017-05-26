"""
Module for a subscription object, which manages a podcast URL, name, and information about how
many episodes of the podcast we have.
"""
import collections
import datetime
import enum
import logging
import os
import platform
import textwrap
import time
from typing import Any, Dict, List, Mapping, Tuple, MutableSequence

import feedparser
import requests

import puckfetcher.constants as constants
import puckfetcher.error as error
import puckfetcher.util as util

DATE_FORMAT_STRING = "%Y%m%dT%H:%M:%S.%f"
HEADERS = {"User-Agent": constants.USER_AGENT}
MAX_RECURSIVE_ATTEMPTS = 10
SUMMARY_LIMIT = 15

LOG = logging.getLogger("root")


# TODO describe field members, function parameters in docstrings.
class Subscription(object):
    """Object describing a podcast subscription."""

    def __init__(self, url: str=None, name: str=None, directory: str=None, backlog_limit: int=0,
                 ) -> None:

        # Maintain separate data members for originally provided URL, and URL we may change due to
        # redirects.
        if url is None or url == "":
            msg = f"URL '{url}' is None or empty - can't create subscription."
            raise error.MalformedSubscriptionError(msg)

        # Maintain name of podcast.
        if name is None or name == "":
            msg = f"Name '{name}' is None or empty - can't create subscription."
            raise error.MalformedSubscriptionError(msg)

        # Temporary storage for swapping around urls.
        self.temp_url: str = None

        LOG.debug(f"Storing provided url '{url}'.")
        self.url = url
        self.original_url = url

        LOG.debug(f"Provided name '{name}'.")
        self.name = name

        # Our file downloader.
        self.downloader = util.generate_downloader(HEADERS, self.name)

        # Our wrapper around feedparser's parse for rate limiting.
        self.parser = _generate_feedparser(self.name)

        # Store feed state, including etag/last_modified.
        self.feed_state = _FeedState()

        self.directory = _process_directory(directory)

        self.backlog_limit = backlog_limit

        self.use_title_as_filename: bool = None

        feedparser.USER_AGENT = constants.USER_AGENT

    @classmethod
    def decode_subscription(cls, sub_dictionary: Mapping[str, Any]) -> "Subscription":
        """Decode subscription from dictionary."""
        url = sub_dictionary.get("url", None)
        if url is None:
            msg = "URL in subscription to decode is null. Cannot decode."
            raise error.MalformedSubscriptionError(msg)

        name = sub_dictionary.get("name", None)
        if name is None:
            msg = "Name in subscription to decode is null. Cannot decode."
            raise error.MalformedSubscriptionError(msg)

        original_url = sub_dictionary.get("original_url", None)
        directory = sub_dictionary.get("directory", None)
        backlog_limit = sub_dictionary.get("backlog_limit", 0)
        use_title_as_filename = sub_dictionary.get("use_title_as_filename", False)
        feed_state = _FeedState(feedstate_dict=sub_dictionary.get("feed_state", None))

        sub = Subscription(url=url, name=name, directory=directory, backlog_limit=backlog_limit)

        sub.original_url = original_url
        sub.use_title_as_filename = use_title_as_filename
        sub.feed_state = feed_state

        # Generate data members that shouldn't/won't be cached.
        sub.downloader = util.generate_downloader(HEADERS, sub.name)

        return sub

    @classmethod
    def encode_subscription(cls, sub: "Subscription") -> Mapping[str, Any]:
        """Encode subscription to dictionary."""

        return {"__type__": "subscription",
                "__version__": constants.VERSION,
                "url": sub.url,
                "original_url": sub.original_url,
                "directory": sub.directory,
                "backlog_limit": sub.backlog_limit,
                "use_title_as_filename": sub.use_title_as_filename,
                "feed_state": sub.feed_state.as_dict(),
                "name": sub.name}

    @staticmethod
    def parse_from_user_yaml(sub_yaml: Mapping[str, Any],
                             defaults: Mapping[str, Any],
                             ) -> "Subscription":
        """
        Parse YAML user-provided subscription into a subscription object, using config-provided
        options as defaults.
        Return None instead of a subscription if we were not able to parse something.
        """

        if "name" not in sub_yaml:
            msg = "No name provided in config file. Cannot create subscription."
            raise error.MalformedSubscriptionError(msg)

        if "url" not in sub_yaml:
            msg = "No URL provided in config file. Cannot create subscription."
            raise error.MalformedSubscriptionError(msg)

        name = sub_yaml["name"]
        url = sub_yaml["url"]
        directory = sub_yaml.get("directory", os.path.join(defaults["directory"], name))
        backlog_limit = sub_yaml.get("backlog_limit", defaults["backlog_limit"])

        sub = Subscription(url=url, name=name, directory=directory, backlog_limit=backlog_limit)

        sub.original_url = sub_yaml["url"]
        sub.use_title_as_filename = sub_yaml.get("use_title_as_filename",
                                                 defaults["use_title_as_filename"])

        return sub

    # "Public" functions.
    def latest(self) -> int:
        """Return latest entry number."""
        return self.feed_state.latest_entry_number

    def attempt_update(self) -> bool:
        """Attempt to download new entries for a subscription."""

        # Attempt to populate self.feed_state from subscription URL.
        feed_get_result = self.get_feed()
        if feed_get_result not in (UpdateResult.SUCCESS, UpdateResult.UNNEEDED):
            return False

        LOG.info(f"Subscription {self.name} got updated feed.")

        # Only consider backlog if we don't have a latest entry number already.
        number_feeds = len(self.feed_state.entries)
        if self.latest() is None:
            if self.backlog_limit is None:
                self.feed_state.latest_entry_number = 0
                LOG.info(
                    textwrap.dedent(
                        f"""\
                        Interpreting 'None' backlog limit as "No Limit" and downloading full
                        backlog ({number_feeds} entries).\
                        """))

            elif self.backlog_limit < 0:
                LOG.error(f"Invalid backlog limit {self.backlog_limit}, downloading nothing.")
                return False

            elif self.backlog_limit > 0:
                LOG.info(f"Backlog limit provided as '{self.backlog_limit}'")
                self.backlog_limit = util.max_clamp(self.backlog_limit, number_feeds)
                LOG.info(f"Backlog limit clamped to '{self.backlog_limit}'")
                self.feed_state.latest_entry_number = number_feeds - self.backlog_limit

            else:
                self.feed_state.latest_entry_number = number_feeds
                LOG.info(
                    textwrap.dedent(
                        f"""\
                        Download backlog for {self.name} is zero.
                        Not downloading backlog but setting number downloaded to {self.latest()}.\
                        """))

        if self.latest() >= number_feeds:
            LOG.info(
                textwrap.dedent(
                    f"""\
                    Number downloaded for {self.name} matches feed entry count {number_feeds}.
                    Nothing to do.\
                    """))
            return True

        number_to_download = number_feeds - self.latest()
        LOG.info(
            textwrap.dedent(
                f"""\
                Number of downloaded feeds for {self.name} is {self.latest()},
                {number_to_download} less than feed entry count {number_feeds}.
                Downloading {number_to_download} entries.\
                """))

        # Queuing feeds in order of age makes the most sense for RSS feeds, so we do that.
        for i in range(self.latest(), number_feeds):
            self.feed_state.queue.append(i + 1)

        self.download_queue()

        return True

    def download_queue(self) -> None:
        """
        Download feed enclosure(s) for all entries in the queue.
        Map from positive indexing we use in the queue to negative feed age indexing used in feed.
        """

        LOG.info(f"Queue for sub {self.name} has {len(self.feed_state.queue)} entries.")

        try:
            while self.feed_state.queue:

                # Pull index from queue, transform from one-indexing to zero-indexing.
                one_indexed_entry_num = self.feed_state.queue.popleft()
                entry_num = one_indexed_entry_num - 1

                # Fetch matching entry.
                num_entries = len(self.feed_state.entries)

                # Do a bounds check in case we accidentally let something bad into the queue.
                if entry_num < 0 or entry_num >= num_entries:
                    LOG.debug(f"Invalid num {one_indexed_entry_num} in queue - skipping.")
                    continue

                entry_age = num_entries - (one_indexed_entry_num)
                entry = self.feed_state.entries[entry_age]

                # Don't overwrite files if we have the matching entry downloaded already, according
                # to records.
                if self.feed_state.entries_state_dict.get(entry_num, False):
                    LOG.info(
                        textwrap.dedent(
                            f"""\
                            SKIPPING entry number {one_indexed_entry_num} (age {entry_age})
                            for '{self.name}' - it's recorded as downloaded.\
                            """))

                else:
                    urls = entry["urls"]
                    num_entry_files = len(urls)

                    LOG.info(
                        textwrap.dedent(
                            f"""\
                            Trying to download entry number {one_indexed_entry_num}
                            (age {entry_age}) for '{self.name}'.\
                            """))

                    # Create directory just for enclosures for this entry if there are many.
                    directory = self.directory
                    if num_entry_files > 1:
                        directory = os.path.join(directory, entry["title"])
                        msg = f"Creating directory to store {num_entry_files} enclosures."
                        LOG.info(msg)

                    for i, url in enumerate(urls):
                        if num_entry_files > 1:
                            LOG.info(f"Downloading enclosure {i+1} of {num_entry_files}.")

                        LOG.debug(f"Extracted url {url} from enclosure.")

                        # TODO catch errors? What if we try to save to a nonsense file?
                        dest = self._get_dest(url, entry["title"], directory)
                        self.downloader(url=url, dest=dest)

                    if one_indexed_entry_num > self.feed_state.latest_entry_number:
                        self.feed_state.latest_entry_number = one_indexed_entry_num
                        LOG.info(f"Have {one_indexed_entry_num} entries for {self.name}.")

                    # Update various things now that we've downloaded a new entry.
                    self.feed_state.entries_state_dict[entry_num] = True
                    self.feed_state.summary_queue.append({"number": one_indexed_entry_num,
                                                          "name": entry["title"],
                                                          "is_this_session": True,
                                                          })

        except KeyboardInterrupt:
            self.feed_state.queue.appendleft(entry_num)

    def enqueue(self, nums: List[int]) -> List[int]:
        """Add entries to this subscription's download queue."""
        actual_nums = _filter_nums(nums, 0, len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            if one_indexed_num not in self.feed_state.queue:
                self.feed_state.queue.append(one_indexed_num)

        LOG.info(f"New queue for {self.name}: {list(self.feed_state.queue)}")

        return actual_nums

    def mark(self, nums: List[int]) -> List[int]:
        """
        Mark entries as downloaded for this subscription. Do not download or do anything else.
        """
        actual_nums = _filter_nums(nums, 0, len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            num = one_indexed_num - 1
            self.feed_state.entries_state_dict[num] = True

        LOG.info(f"Items marked as downloaded for {self.name}: {actual_nums}.")
        return actual_nums

    def unmark(self, nums: List[int]) -> List[int]:
        """
        Mark entries as not downloaded for this subscription. Do not download or do anything else.
        """
        actual_nums = _filter_nums(nums, 0, len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            num = one_indexed_num - 1
            self.feed_state.entries_state_dict[num] = False

        LOG.info(f"Items marked as not downloaded for {self.name}: {actual_nums}.")
        return actual_nums

    def update(self, dir: str=None, config_dir: Any=None, url: str=None,
               set_original: bool=False, name: str=None,
               ) -> None:
        """Update values for this subscription."""
        if dir == "":
            LOG.debug(f"Provided invalid directory '{dir}' for '{self.name}'- ignoring update.")
            return

        if dir is not None:
            dir = util.expand(dir)

            if self.directory != dir:
                if os.path.isabs(dir):
                    self.directory = dir

                else:
                    self.directory = os.path.join(config_dir, dir)

                util.ensure_dir(self.directory)

        if url is not None:
            self.url = url

            if set_original:
                self.original_url = url

        if name is not None:
            self.name = name

    def default_missing_fields(self, settings: Mapping[str, Any]) -> None:
        """Set default values for any fields that are None (ones that were never set)."""

        # NOTE - directory is set separately, because we'll want to create it.
        # The options set here are just plain options.
        if self.backlog_limit is None:
            self.backlog_limit = settings["backlog_limit"]

        if self.use_title_as_filename is None:
            self.use_title_as_filename = settings["use_title_as_filename"]

        if not hasattr(self, "feed_state") or self.feed_state is None:
            self.feed_state = _FeedState()

        self.downloader = util.generate_downloader(HEADERS, self.name)
        self.parser = _generate_feedparser(self.name)

    def get_status(self, index: int, total_subs: int) -> str:
        """Provide status of subscription."""
        pad_num = len(str(total_subs))
        padded_cur_num = str(index + 1).zfill(pad_num)
        one_indexed_entry_num = self.feed_state.latest_entry_number + 1
        return f"{padded_cur_num}/{total_subs} - '{self.name}' |{self.latest()}|"

    def get_details(self, index: int, total_subs: int) -> None:
        """Provide multiline summary of subscription state."""
        detail_lines = []

        detail_lines.append(self.get_status(index, total_subs))

        num_entries = len(self.feed_state.entries)
        pad_num = len(str(num_entries))
        detail_lines.append("Status of podcast queue:")
        detail_lines.append(f"{repr(self.feed_state.queue)}")
        detail_lines.append("")
        detail_lines.append("Status of podcast entries:")

        entry_indicators = []
        for entry in range(num_entries):
            if self.feed_state.entries_state_dict.get(entry, False):
                indicator = "+"
            else:
                indicator = "-"

            entry_indicators.append(f"{str(entry+1).zfill(pad_num)}{indicator}")

        detail_lines.append(" ".join(entry_indicators))
        details = "\n".join(detail_lines)
        LOG.info(details)

    def get_feed(self, attempt_count: int=0) -> "UpdateResult":
        """Get RSS structure for this subscription. Return status code indicating result."""
        res = None
        if attempt_count > MAX_RECURSIVE_ATTEMPTS:
            LOG.debug(
                textwrap.dedent(
                    f"""\
                    Too many recursive attempts ({attempt_count}) to get feed for sub
                    {self.name}, canceling.\
                    """))
            res = UpdateResult.FAILURE

        elif self.url is None or self.url == "":
            LOG.debug(f"URL {self.url} is empty , cannot get feed for sub {self.name}.")
            res = UpdateResult.FAILURE

        if res is not None:
            return res

        else:
            LOG.info(f"Getting entries (attempt {attempt_count}) for {self.name} from {self.url}.")

        (parsed, code) = self._feedparser_parse_with_options()
        if code == UpdateResult.UNNEEDED:
            LOG.info("We have the latest feed, nothing to do.")
            return code

        elif code != UpdateResult.SUCCESS:
            LOG.info(f"Feedparser parse failed ({code}), aborting.")
            return code

        LOG.debug("Feedparser parse succeeded.")

        # Detect some kinds of HTTP status codes signaling failure.
        code = self._handle_http_codes(parsed)
        if code == UpdateResult.ATTEMPT_AGAIN:
            LOG.debug("Transient HTTP error, attempting again.")
            temp = self.temp_url
            code = self.get_feed(attempt_count=attempt_count + 1)
            if temp is not None:
                self.url = temp

        elif code != UpdateResult.SUCCESS:
            LOG.debug(f"Ran into HTTP error ({code}), aborting.")

        else:
            self.feed_state.load_rss_info(parsed)

        return code

    def session_summary(self) -> List[str]:
        """Provide items downloaded in this session in convenient form."""
        return [f"{item['name']} (#{item['number']})"
                for item in self.feed_state.summary_queue
                if item["is_this_session"]]

    def full_summary(self) -> List[str]:
        """Provide items downloaded recently in convenient form."""
        return [f"{item['name']} (#{item['number']})" for item in self.feed_state.summary_queue]

    def as_config_yaml(self) -> Mapping[str, Any]:
        """Return self as config file YAML."""

        return {"url": self.original_url,
                "name": self.name,
                "backlog_limit": self.backlog_limit,
                "directory": self.directory}

    # "Private" class functions (messy internals).
    def _feedparser_parse_with_options(self) -> Tuple[feedparser.FeedParserDict, "UpdateResult"]:
        """
        Perform a feedparser parse, providing arguments (like etag) we might want it to use.
        Don't provide etag/last_modified if the last get was unsuccessful.
        """
        if self.feed_state.last_modified is not None:
            last_mod = self.feed_state.last_modified.timetuple()
        else:
            last_mod = None

        # NOTE - this naming is a bit confusing here - parser is really a thing you call with
        # arguments to get a feedparser result.
        # Maybe better called parser-generator, or parse-performer or something?
        parsed = self.parser(self.url, self.feed_state.etag, last_mod)

        self.feed_state.etag = parsed.get("etag", self.feed_state.etag)
        self.feed_state.store_last_modified(parsed.get("modified_parsed", None))

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if "status" not in parsed and parsed.get("bozo", None) == 1:
            # NOTE: Feedparser documentation indicates that you can always call getMessage, but
            # it's possible for feedparser to spit out a URLError, which doesn't have getMessage.
            # Catch this case.
            if hasattr(parsed.bozo_exception, "getMessage()"):
                msg = parsed.bozo_exception.getMessage()

            else:
                msg = repr(parsed.bozo_exception)

            LOG.info(f"Unable to retrieve feed for {self.name} from {self.url}.")
            LOG.debug(f"Update failed because bozo exception {msg} occurred.")
            return (None, UpdateResult.FAILURE)

        elif parsed.get("status") == requests.codes["NOT_MODIFIED"]:
            LOG.debug("No update to feed, nothing to do.")
            return (None, UpdateResult.UNNEEDED)

        else:
            return (parsed, UpdateResult.SUCCESS)

    def _handle_http_codes(self, parsed: feedparser.FeedParserDict) -> "UpdateResult":
        """
        Given feedparser parse result, determine if parse succeeded, and what to do about that.
        """
        # Feedparser gives no status if you feedparse a local file.
        if "status" not in parsed:
            LOG.debug("Saw status 200 - OK, all is well.")
            return UpdateResult.SUCCESS

        status = parsed.get("status", 200)
        result = UpdateResult.SUCCESS
        if status == requests.codes["NOT_FOUND"]:
            LOG.error(
                textwrap.dedent(
                    f"""\
                    Saw status {status}, unable to retrieve feed text for {self.name}.
                    Stored URL {self.url} for {self.name} will be preserved
                    and checked again on next attempt.\
                    """))

            result = UpdateResult.FAILURE

        elif status in [requests.codes["UNAUTHORIZED"], requests.codes["GONE"]]:
            LOG.error(
                textwrap.dedent(
                    f"""\
                    Saw status {status}, unable to retrieve feed text for {self.name}.
                    Clearing stored URL {self.url} for {self.name}.
                    Please provide new URL and authorization for subscription {self.name}.\
                    """))

            self.url = None
            result = UpdateResult.FAILURE

        # Handle redirecting errors
        elif status in [requests.codes["MOVED_PERMANENTLY"], requests.codes["PERMANENT_REDIRECT"]]:
            LOG.warning(
                textwrap.dedent(
                    f"""\
                    Saw status {status} indicating permanent URL change.
                    Changing stored URL {self.url} for {self.name} to {parsed.get('href')}
                    and attempting get with new URL.\
                    """))

            self.url = parsed.get("href")
            result = UpdateResult.ATTEMPT_AGAIN

        elif status in [requests.codes["FOUND"], requests.codes["SEE_OTHER"],
                        requests.codes["TEMPORARY_REDIRECT"]]:
            LOG.warning(
                textwrap.dedent(
                    f"""\
                    Saw status {status} indicating temporary URL change.
                    Attempting with new URL {parsed.get('href')}.
                    Stored URL {self.url} for {self.name} will be unchanged.\
                    """))

            self.temp_url = self.url
            self.url = parsed.get("href")
            result = UpdateResult.ATTEMPT_AGAIN

        elif status != 200:
            LOG.warning(f"Saw '{status}'. Retrying retrieve for {self.name} at {self.url}.")
            result = UpdateResult.ATTEMPT_AGAIN

        else:
            LOG.debug("Saw status 200. Success!")

        return result

    def _get_dest(self, url: str, title: str, directory: str) -> str:

        # URL example: "https://www.example.com/foo.mp3?test=1"

        # Cut everything but filename and (possibly) query params.
        # URL example: "foo.mp3?test=1"
        url_end = url.split("/")[-1]

        # URL example: "foo.mp3?test=1"
        # Cut query params.
        # I think I could assume there's only one '?' after the file extension, but after being
        # surprised by query parameters, I want to be extra careful.
        # URL example: "foo.mp3"
        url_filename = url_end.split("?")[0]

        filename = url_filename

        if platform.system() == "Windows":
            LOG.error(textwrap.dedent(
                """\
                Sorry, we can't guarantee valid filenames on Windows if we use RSS
                subscription titles.
                We'll support it eventually!
                Using URL filename.\
                """))

        elif self.use_title_as_filename:
            ext = os.path.splitext(url_filename)[1][1:]
            filename = f"{title}.{ext}"  # RIP owl

        # Remove characters we can't allow in filenames.
        filename = util.sanitize(filename)

        return os.path.join(directory, filename)

    def __eq__(self, rhs: Any) -> bool:
        return isinstance(rhs, Subscription) and repr(self) == repr(rhs)

    def __ne__(self, rhs: Any) -> bool:
        return not self.__eq__(rhs)

    def __repr__(self) -> str:
        return str(Subscription.encode_subscription(self))


class _FeedState(object):
    def __init__(self, feedstate_dict: Mapping[str, Any]=None) -> None:
        if feedstate_dict is not None:
            LOG.debug("Successfully loaded feed state dict.")

            self.feed = feedstate_dict.get("feed", {})
            self.entries = feedstate_dict.get("entries", [])
            self.entries_state_dict = feedstate_dict.get("entries_state_dict", {})
            self.queue = collections.deque(feedstate_dict.get("queue", []))

            # Store the most recent SUMMARY_LIMIT items we've downloaded.
            temp_list = feedstate_dict.get("summary_queue", [])
            self.summary_queue: MutableSequence[Dict[str, Any]] = collections.deque(
                [],
                SUMMARY_LIMIT,
            )

            # When we load from the cache file, mark all of the items in the summary queue as not
            # being from the current session.
            for elem in temp_list:
                elem["is_this_session"] = False
                self.summary_queue.append(elem)

            last_modified = feedstate_dict.get("last_modified", None)
            self.store_last_modified(last_modified)

            self.etag = feedstate_dict.get("etag", None)
            self.latest_entry_number = feedstate_dict.get("latest_entry_number", None)

        else:
            LOG.debug("Did not successfully load feed state dict.")
            LOG.debug("Creating blank dict.")

            self.feed = {}
            self.entries = []
            self.entries_state_dict = {}
            self.queue = collections.deque([])
            self.summary_queue = collections.deque([], SUMMARY_LIMIT)
            self.last_modified: Any = None
            self.etag: str = None
            self.latest_entry_number = None

    def load_rss_info(self, parsed: feedparser.FeedParserDict) -> None:
        """Load some RSS subscription elements into this feed state."""
        self.entries = []
        for entry in parsed.get("entries"):
            new_entry = {}
            new_entry["title"] = entry["title"]

            new_entry["urls"] = []
            for enclosure in entry["enclosures"]:
                new_entry["urls"].append(enclosure["href"])

            self.entries.append(new_entry)

    def as_dict(self) -> Dict[str, Any]:
        """Return dictionary of this feed state object."""

        return {"entries": self.entries,
                "entries_state_dict": self.entries_state_dict,
                "queue": list(self.queue),
                "latest_entry_number": self.latest_entry_number,
                "summary_queue": list(self.summary_queue),
                "last_modified": None,
                "etag": self.etag,
                }

    def store_last_modified(self, last_modified: Any) -> None:
        """Store last_modified as a datetime, regardless of form it's provided in."""
        if isinstance(last_modified, time.struct_time):
            LOG.debug("Updated last_modified.")
            self.last_modified = datetime.datetime.fromtimestamp(time.mktime(last_modified))
        else:
            LOG.debug("Unhandled 'last_modified' type, ignoring.")
            self.last_modified = None


# "Private" file functions (messy internals).
def _process_directory(directory: str) -> str:
    """Assign directory if none was given, and create directory if necessary."""
    directory = util.expand(directory)
    if directory is None:
        LOG.debug(f"No directory provided, defaulting to {directory}.")
        return util.expand(constants.APPDIRS.user_data_dir)

    LOG.debug(f"Using directory {directory}.")

    util.ensure_dir(directory)

    return directory


def _filter_nums(nums: List[int], min_lim: int, max_lim: int) -> List[int]:
    """Given two limits, remove elements from the list that aren't in that range."""
    return [num for num in nums if num > min_lim and num <= max_lim]

def _generate_feedparser(name: str) -> Any:
    """Perform rate-limited parse with feedparser."""

    @util.rate_limited(120, name)
    def _rate_limited_parser(url: str, etag: str, last_modified: Any) -> feedparser.FeedParserDict:
        # pylint: disable=no-member
        return feedparser.parse(url, etag=etag, modified=last_modified)

    return _rate_limited_parser


# pylint: disable=too-few-public-methods
class UpdateResult(enum.Enum):
    """Enum describing possible results of trying to update a subscription."""
    SUCCESS = 0
    UNNEEDED = -1
    FAILURE = -2
    ATTEMPT_AGAIN = -3
