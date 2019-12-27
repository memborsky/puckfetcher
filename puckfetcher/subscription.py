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
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple, MutableSequence

import drewtilities as util
import feedparser
import magic
import requests
import stagger

import puckfetcher.constants as constants
import puckfetcher.error as error

DATE_FORMAT_STRING = "%Y%m%dT%H:%M:%S.%f"
HEADERS = {"User-Agent": constants.USER_AGENT}
MAX_RECURSIVE_ATTEMPTS = 10
SUMMARY_LIMIT = 15

LOG = logging.getLogger("root")


# TODO describe field members, function parameters in docstrings.
class Subscription(object):
    """Object describing a podcast subscription."""

    def __init__(self, url: str=None, name: str=None, directory: str=None) -> None:
        """
        Object constructor for subscription.

        :param url: URL of subscription. Required.
        :param name: Name of scription, used as identifier. Required.
        :param directory: Storage directory for subscription. Will otherwise be based on name.
        """
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
        self.temp_url: str = ""

        LOG.debug(f"Storing provided url '{url}'.")
        self.url = url
        self.original_url = url

        LOG.debug(f"Storing provided name '{name}'.")
        self.metadata = {
            "name": name,
            "artist": "",
            "album": name,
            "album_artist": "",
        }

        # Our file downloader.
        self.downloader = util.generate_downloader(HEADERS, self.metadata["name"])
        feedparser.USER_AGENT = constants.USER_AGENT

        # Our wrapper around feedparser's parse for rate limiting.
        self.parser = _generate_feedparser(self.metadata["name"])

        # Store feed state, including etag/last_modified.
        self.feed_state = _FeedState()

        self.directory = _process_directory(directory)

        self.settings: Dict[str, Any] = {
            "use_title_as_filename": None,
            "backlog_limit": 0,
            "set_tags": False,
            "overwrite_title": False,
        }

    @classmethod
    def decode_subscription(cls, sub_dictionary: Mapping[str, Any]) -> "Subscription":
        """
        Decode subscription from dictionary.

        :param sub_dictionary: Dictionary from JSON to use to decode object.
        :returns: Subscription object built from dictionary.
        """
        url = sub_dictionary.get("url", None)
        if url is None:
            msg = "URL in subscription to decode is null. Cannot decode."
            raise error.MalformedSubscriptionError(msg)

        original_url = sub_dictionary.get("original_url", None)
        directory = sub_dictionary.get("directory", None)
        feed_state = _FeedState(feedstate_dict=sub_dictionary.get("feed_state", None))

        name = sub_dictionary.get("name", None)
        if name is None:
            msg = "Name in subscription to decode is null. Cannot decode."
            raise error.MalformedSubscriptionError(msg)

        sub = Subscription(url=url, name=name, directory=directory)

        sub.original_url = original_url
        sub.feed_state = feed_state

        if "settings" in sub_dictionary.keys():
            sub.settings = sub_dictionary["settings"]
        else:
            sub.settings = {
                "use_title_as_filename": sub_dictionary.get("use_title_as_filename", False),
                "backlog_limit": sub_dictionary.get("backlog_limit", 0),
                "set_tags": sub_dictionary.get("set_tags", False),
                "overwrite_title": sub_dictionary.get("overwrite_title", False),
            }

        if "metadata" in sub_dictionary.keys():
            sub.metadata = sub_dictionary["metadata"]
        else:
            sub.metadata = {
                "name": name,
                "artist": sub_dictionary.get("artist", ""),
                "album": sub_dictionary.get("album", name),
                "album_artist": sub_dictionary.get("album_artist", ""),
            }

        # Generate data members that shouldn't/won't be cached.
        sub.downloader = util.generate_downloader(HEADERS, sub.metadata["name"])

        return sub

    @classmethod
    def encode_subscription(cls, sub: "Subscription") -> Mapping[str, Any]:
        """
        Encode subscription to dictionary.

        :param sub: Subscription object to turn into a dictionary.
        :returns: A dictionary that can be written to JSON or passed around.
        """

        return {
            "__type__": "subscription",
            "__version__": constants.VERSION,
            "url": sub.url,
            "original_url": sub.original_url,
            "directory": sub.directory,
            "settings": sub.settings,
            "feed_state": sub.feed_state.as_dict(),
            "metadata": sub.metadata,
            "name": sub.metadata["name"],
        }

    @staticmethod
    def parse_from_user_yaml(
            sub_yaml: Mapping[str, Any],
            defaults: Mapping[str, Any],
    ) -> "Subscription":
        """
        Parse YAML user-provided subscription into a subscription object, using config-provided
        options as defaults.

        :param sub_yaml: Dictionary from user config file to use to build subscription.
        :param defaults: Default values for all fields to substitute for what user didn't provide.
        :returns: Subscription object based on user config and defaults.
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

        sub = Subscription(url=url, name=name, directory=directory)

        sub.original_url = sub_yaml["url"]
        sub.settings["use_title_as_filename"] = sub_yaml.get("use_title_as_filename",
                                                             defaults["use_title_as_filename"])
        sub.settings["backlog_limit"] = sub_yaml.get("backlog_limit", defaults["backlog_limit"])
        sub.settings["set_tags"] = sub_yaml.get("set_tags", defaults["set_tags"])
        sub.settings["overwrite_title"] = sub_yaml.get("overwrite_title", False)

        sub.metadata["name"] = name
        sub.metadata["artist"] = sub_yaml.get("artist", "")
        sub.metadata["album"] = sub_yaml.get("album", name)
        sub.metadata["album_artist"] = sub_yaml.get("album_artist", "")

        return sub

    # "Public" functions.
    def latest(self) -> int:
        """
        Return latest entry number.

        :returns: Latest entry number for this subscription.
        """
        return self.feed_state.latest_entry_number

    def attempt_update(self) -> bool:
        """
        Attempt to download new entries for a subscription.

        :returns: Whether update succeeded or failed.
        """

        # Attempt to populate self.feed_state from subscription URL.
        feed_get_result = self.get_feed()
        if feed_get_result not in (UpdateResult.SUCCESS, UpdateResult.UNNEEDED):
            return False

        LOG.info(f"Subscription {self.metadata['name']} got updated feed.")

        # Only consider backlog if we don't have a latest entry number already.
        number_feeds = len(self.feed_state.entries)
        if self.latest() is None:
            if self.settings["backlog_limit"] is None:
                self.feed_state.latest_entry_number = 0
                LOG.info(f"Interpreting 'None' backlog limit as 'No Limit' and downloading full "
                         f"backlog ({number_feeds} entries).")

            elif self.settings["backlog_limit"] < 0:
                LOG.error(f"Invalid backlog limit {self.settings['backlog_limit']}, "
                          f"downloading nothing.")
                return False

            elif self.settings["backlog_limit"] > 0:
                LOG.info(f"Backlog limit provided as '{self.settings['backlog_limit']}'")
                self.settings["backlog_limit"] = util.max_clamp(self.settings["backlog_limit"],
                                                                number_feeds)
                LOG.info(f"Backlog limit clamped to '{self.settings['backlog_limit']}'")
                self.feed_state.latest_entry_number = number_feeds - self.settings["backlog_limit"]

            else:
                self.feed_state.latest_entry_number = number_feeds
                LOG.info(f"Download backlog for {self.metadata['name']} is zero."
                         f"\nNot downloading backlog but setting number downloaded to "
                         f"{self.latest()}.")

        if self.latest() >= number_feeds:
            LOG.info(f"Num downloaded for {self.metadata['name']} matches feed "
                     f"entry count {number_feeds}."
                     f"\nNothing to do.")
            return True

        number_to_download = number_feeds - self.latest()
        LOG.info(f"Number of downloaded feeds for {self.metadata['name']} is {self.latest()}, "
                 f"{number_to_download} less than feed entry count {number_feeds}."
                 f"\nDownloading {number_to_download} entries.")

        # Queuing feeds in order of age makes the most sense for RSS feeds, so we do that.
        for i in range(self.latest(), number_feeds):
            self.feed_state.queue.append(i + 1)

        self.download_queue()

        return True

    def download_queue(self) -> None:
        """
        Download feed enclosure(s) for all entries in the queue.
        """

        LOG.info(f"Queue for sub {self.metadata['name']} "
                 f"has {len(self.feed_state.queue)} entries.")

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
                    LOG.info(f"SKIPPING entry number {one_indexed_entry_num} (age {entry_age}) "
                             f"for '{self.metadata['name']}' - it's recorded as downloaded.")

                else:
                    urls = entry["urls"]
                    num_entry_files = len(urls)

                    LOG.info(f"Trying to download entry number {one_indexed_entry_num}"
                             f"(age {entry_age}) for '{self.metadata['name']}'.")

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
                        dest = self._get_dest(url=url, title=entry["title"], directory=directory)
                        self.downloader(url=url, dest=dest)

                        self.check_tag_edit_safe(dest, entry)

                    if one_indexed_entry_num > self.feed_state.latest_entry_number:
                        self.feed_state.latest_entry_number = one_indexed_entry_num
                        LOG.info(
                            f"Have {one_indexed_entry_num} entries for "
                            f"{self.metadata['name']}.")

                    # Update various things now that we've downloaded a new entry.
                    self.feed_state.entries_state_dict[entry_num] = True
                    self.feed_state.summary_queue.append(
                        {
                            "number": one_indexed_entry_num,
                            "name": entry["title"],
                            "is_this_session": True,
                        })

        except KeyboardInterrupt:
            self.feed_state.queue.appendleft(entry_num)

    def enqueue(self, nums: List[int]) -> List[int]:
        """
        Add entries to this subscription's download queue.

        :param nums: List of episode numbers (numbered from 1 in the RSS feed) to add to queue.
        :returns: List of episode numbers added to queue.
            Duplicates and items already in queue will be ignored,
            as will numbers out-of-bounds.
        """
        actual_nums = _filter_nums(nums=nums, max_lim=len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            if one_indexed_num not in self.feed_state.queue:
                self.feed_state.queue.append(one_indexed_num)

        LOG.info(f"New queue for {self.metadata['name']}: {list(self.feed_state.queue)}")

        return actual_nums

    def mark(self, nums: List[int]) -> List[int]:
        """
        Mark entries as downloaded for this subscription. Do not download or do anything else.

        :param nums: List of episode numbers (numbered from 1 in the RSS feed) to mark as
            downloaded.
        :returns: List of episode numbers marked as downloaded.
            Items out-of-bounds will be ignored.
        """
        actual_nums = _filter_nums(nums=nums, max_lim=len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            num = one_indexed_num - 1
            self.feed_state.entries_state_dict[num] = True

        LOG.info(f"Items marked as downloaded for {self.metadata['name']}: {actual_nums}.")
        return actual_nums

    def unmark(self, nums: List[int]) -> List[int]:
        """
        Mark entries as not downloaded for this subscription.
        Do not download or do anything else.

        :param nums: List of episode numbers (numbered from 1 in the RSS feed) to unmark as
            downloaded.
        :returns: List of episode numbers unmarked as downloaded.
            Items out-of-bounds will be ignored.
        """
        actual_nums = _filter_nums(nums=nums, max_lim=len(self.feed_state.entries))

        for one_indexed_num in actual_nums:
            num = one_indexed_num - 1
            self.feed_state.entries_state_dict[num] = False

        LOG.info(f"Items marked as not downloaded for {self.metadata['name']}: {actual_nums}.")
        return actual_nums

    def update(
            self,
            *,
            directory: str=None,
            config_dir: Any=None,
            url: str=None,
            set_original: bool=False,
            name: str=None,
            settings: Mapping[str, Any]=None,
            metadata: Mapping[str, Any]=None,
    ) -> None:
        """
        Update values for this subscription.
        If a value is not provided,
        the corresponding property will not be updated.

        :param directory: New directory for subscription.
        :param config_dir: New config_dir for subscription.
        :param url: New url for subscription.
        :param set_original: When provided with new url,
            will update the original_url property as well.
        :param name: New name for subscription.
        :param settings: New settings to merge with current settings.
        :param metadata: New metadata to merge with current metadata.
        """
        if directory == "":
            directory = None

        if config_dir is None:
            config_dir = "."

        if directory is not None:
            d = util.expand(directory)

            if self.directory != d:
                if os.path.isabs(d):
                    self.directory = d

                else:
                    self.directory = os.path.join(config_dir, d)

                util.ensure_dir(self.directory)

        if url is not None:
            self.url = url

            if set_original:
                self.original_url = url

        if settings is not None:
            self.settings = {**self.settings, **settings}

        if metadata is not None:
            self.metadata = {**self.metadata, **metadata}

    def default_missing_fields(self, settings: Mapping[str, Any]) -> None:
        """
        Set default values for any fields that are None (ones that were never set).

        :param settings: New settings to override unset ones.
        """
        # NOTE - directory is set separately, because we'll want to create it.
        # The options set here are just plain options.
        if self.settings["backlog_limit"] is None:
            self.settings["backlog_limit"] = settings["backlog_limit"]

        if self.settings["use_title_as_filename"] is None:
            self.settings["use_title_as_filename"] = settings["use_title_as_filename"]

        if not hasattr(self, "feed_state") or self.feed_state is None:
            self.feed_state = _FeedState()

        self.downloader = util.generate_downloader(HEADERS, self.metadata["name"])
        self.parser = _generate_feedparser(self.metadata["name"])

    def get_status(self, index: int, total_subs: int) -> str:
        """
        Provide status of subscription.

        :param index: Index of this subscription,
            used for display purposes.
        :param total_subs: Total number of subscriptions,
            used for display purposes.
        :returns: String with display numbers,
            name,
            and latest entry number.
        """
        one_indexed_indent = index + 1
        pad_num = len(str(total_subs))
        padded_cur_num = str(one_indexed_indent).zfill(pad_num)
        if self.latest() is not None:
            one_indexed_entry_num = self.latest() + 1
        else:
            one_indexed_entry_num = self.latest()
        return f"{padded_cur_num}/{total_subs} - '{self.metadata['name']}' " + \
                f"|{one_indexed_entry_num}|"

    def get_details(self, index: int, total_subs: int) -> None:
        """
        Provide multiline summary of subscription state.

        :param index: Index of this subscription,
            used for display purposes.
        :param total_subs: Total number of subscriptions,
            used for display purposes.
        :returns: Multiline string containing oneline status,
            this subscription's queue,
            and the state of this subscription's entries.
        """
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
        """
        Get latest RSS structure for this subscription.
        Return status code indicating result.

        :param attempt_count: Number of times to attempt.
        :returns: UpdateResult status code.
        """
        res = None
        if attempt_count > MAX_RECURSIVE_ATTEMPTS:
            LOG.debug(f"Too many recursive attempts ({attempt_count}) to get feed for sub"
                      f"{self.metadata['name']}, canceling.")
            res = UpdateResult.FAILURE

        elif self.url is None or self.url == "":
            LOG.debug(f"URL {self.url} is empty , cannot get feed for sub "
                      f"{self.metadata['name']}.")
            res = UpdateResult.FAILURE

        if res is not None:
            return res

        else:
            LOG.info(f"Getting entries (attempt {attempt_count}) for {self.metadata['name']} "
                     f"from {self.url}.")

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
        """
        Provide items downloaded in this session in convenient form.

        :returns: List of name/number strings for items downloaded this session.
        """
        return [f"{item['name']} (#{item['number']})"
                for item in self.feed_state.summary_queue
                if item["is_this_session"]]

    def full_summary(self) -> List[str]:
        """
        Provide items downloaded recently in convenient form.

        :returns: List of name/number strings for items in the summary queue.
        """
        return [f"{item['name']} (#{item['number']})" for item in self.feed_state.summary_queue]

    def check_tag_edit_safe(self, dest: str, entry: Mapping[str, Any]) -> None:
        """
        Check if we can safely edit ID3v2 tags.
        Will do nothing if this is not an MP3 file.

        :param dest: File to change tags on.
        :param entry: Entry from RSS feed to use,
            alongside metadata,
            to populate ID3v2 tags.
        """
        # need to test this is an MP3 file first.
        magic_res = magic.from_file(dest)

        # love 2 parse files
        # we're fairly conservative here, because I would rather not put tags in
        # than accidentally break a file.
        mp3_signifiers = [
            "MPEG ADTS, layer III",
            "Audio file with ID3",
        ]

        file_is_mp3 = False
        for signifier in mp3_signifiers:
            if signifier in magic_res:
                file_is_mp3 = True
                break

        if not file_is_mp3:
            LOG.info(
                f"Skipping adding tags for {dest}, "
                "because it doesn't seem to be an mp3 file."
            )
            return

        LOG.info(f"Editing tags for {dest}.")
        self.process_tags(dest, entry)

    def process_tags(self, dest: str, entry: Mapping[str, Any]) -> None:
        """
        Set ID3v2 tags on downloaded MP3 file.

        :param dest: File to change tags on.
        :param entry: Entry from RSS feed to use,
            alongside metadata,
            to populate ID3v2 tags.
        """
        try:
            tag = stagger.read_tag(dest)
        except stagger.errors.NoTagError as e:
            LOG.debug(f"No tag present, creating one: {e}")
            tag = stagger.Tag24()

        # Process tags. If set to set_tags and tags are empty, write tags.
        # Pull tags into sub metadata if it's not set.
        # Pull tags into entry unless they're empty, and then try sub.
        LOG.info(f"Artist tag is '{tag.artist}'.")
        if tag.artist == "" and self.settings["set_tags"]:
            LOG.info(f"Setting artist tag to '{self.metadata['artist']}'.")
            tag.artist = self.metadata["artist"]

        if self.metadata["artist"] == "":
            self.metadata["artist"] = tag.artist

        if tag.artist != "":
            entry["metadata"]["artist"] = tag.artist
        else:
            entry["metadata"]["artist"] = self.metadata["artist"]

        LOG.info(f"Album tag is '{tag.album}'.")
        if tag.album == "":
            LOG.info(f"Setting album tag to '{self.metadata['album']}'.")
            tag.album = self.metadata["album"]

        if self.metadata["album"] == "":
            self.metadata["album"] = tag.album

        if tag.album != "":
            entry["metadata"]["album"] = tag.album
        else:
            entry["metadata"]["album"] = self.metadata["album"]

        LOG.info(f"Album Artist tag is '{tag.album_artist}'.")
        if tag.album_artist == "":
            LOG.info(f"Setting album_artist tag to '{self.metadata['album_artist']}'.")
            tag.album_artist = self.metadata["album_artist"]

        if self.metadata["album_artist"] == "":
            self.metadata["album_artist"] = tag.album_artist

        if tag.album_artist != "":
            entry["metadata"]["album_artist"] = tag.album_artist
        else:
            entry["metadata"]["album_artist"] = self.metadata["album_artist"]

        LOG.info(f"Title tag is '{tag.title}'.")
        LOG.info(f"Overwrite setting is set to '{self.settings['overwrite_title']}'.")
        if tag.title == "" or self.settings["overwrite_title"]:
            LOG.info(f"Setting title tag to '{entry['title']}'.")
            tag.title = entry["title"]

        # Store some extra tags on the entry. Doesn't matter if they're empty, they're empty on the
        # entry too.
        entry["metadata"]["genre"] = tag.genre
        entry["metadata"]["date"] = tag.date

        tag.write(filename=dest)

    def as_config_yaml(self) -> Mapping[str, Any]:
        """
        Return self as config file YAML-ready dictionary.

        :returns: Dict of parameters ready for YAML.
        """
        return {
            "url": self.original_url,
            "name": self.metadata["name"],
            "artist": self.metadata["artist"],
            "album": self.metadata["album"],
            "album_artist": self.metadata["album_artist"],
            "backlog_limit": self.settings["backlog_limit"],
            "set_tags": self.settings["set_tags"],
            "overwrite_title": self.settings["overwrite_title"],
            "directory": self.directory
        }

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

            LOG.info(f"Unable to retrieve feed for {self.metadata['name']} from {self.url}.")
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
        # feedparser gives no status if you feedparse a local file.
        if "status" not in parsed:
            LOG.debug("Saw status 200 - OK, all is well.")
            return UpdateResult.SUCCESS

        status = parsed.get("status", 200)
        result = UpdateResult.SUCCESS
        if status == requests.codes["NOT_FOUND"]:
            LOG.error(f"Saw status {status}, unable to retrieve feed text for "
                      f"{self.metadata['name']}."
                      f"\nStored URL {self.url} for {self.metadata['name']} will be preserved"
                      f"and checked again on next attempt.")

            result = UpdateResult.FAILURE

        elif status in [requests.codes["UNAUTHORIZED"], requests.codes["GONE"]]:
            LOG.error(f"Saw status {status}, unable to retrieve feed text for "
                      f"{self.metadata['name']}."
                      f"\nClearing stored URL {self.url} for {self.metadata['name']}."
                      f"\nPlease provide new URL and authorization for subscription "
                      f"{self.metadata['name']}.")

            self.url = ""
            result = UpdateResult.FAILURE

        # handle redirecting errors
        elif status in [requests.codes["MOVED_PERMANENTLY"], requests.codes["PERMANENT_REDIRECT"]]:
            LOG.warning(f"Saw status {status} indicating permanent URL change."
                        f"\nChanging stored URL {self.url} for {self.metadata['name']} to "
                        f"{parsed.get('href')} and attempting get with new URL.")

            self.url = parsed.get("href")
            result = UpdateResult.ATTEMPT_AGAIN

        elif status in [requests.codes["FOUND"], requests.codes["SEE_OTHER"],
                        requests.codes["TEMPORARY_REDIRECT"]]:
            LOG.warning(f"Saw status {status} indicating temporary URL change."
                        f"\nAttempting with new URL {parsed.get('href')}."
                        f"\nStored URL {self.url} for {self.metadata['name']} will be unchanged.")

            self.temp_url = self.url
            self.url = parsed.get("href")
            result = UpdateResult.ATTEMPT_AGAIN

        elif status != 200:
            LOG.warning(f"Saw '{status}'. Retrying retrieve for {self.metadata['name']} "
                        f"at {self.url}.")
            result = UpdateResult.ATTEMPT_AGAIN

        else:
            LOG.debug("Saw status 200. Success!")

        return result

    def _get_dest(self, url: str, title: str, directory: str) -> str:
        """
        Process url and title and base directory into a full filename,
        suitable for writing to.
        """
        # url example: "https://www.example.com/foo.mp3?test=1"
        # cut everything but filename and (possibly) query params.
        url_end = url.split("/")[-1]

        # url_end example: "foo.mp3?test=1"
        # cut query params.
        # I think I could assume there's only one '?' after the file extension,
        # but after being surprised by query parameters,
        # I want to be extra careful.
        url_filename = url_end.split("?")[0]

        # url_filename example: "foo.mp3"

        # this is one of the parts of the project intended to make it not MP3 specific.
        if self.settings["use_title_as_filename"]:
            ext = os.path.splitext(url_filename)[1][1:]
            filename = f"{title}.{ext}"  # RIP owl

            # remove characters we can't allow in filenames.
            filename = util.sanitize(filename)

        else:
            filename = url_filename

        return os.path.join(directory, filename)

    def __eq__(self, rhs: Any) -> bool:
        return isinstance(rhs, Subscription) and repr(self) == repr(rhs)

    def __ne__(self, rhs: Any) -> bool:
        return not self.__eq__(rhs)

    def __str__(self) -> str:
        return str(Subscription.encode_subscription(self))

    def __repr__(self) -> str:
        return str(self)


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

            self.etag: str = feedstate_dict.get("etag", "")
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
            self.etag = ""
            self.latest_entry_number = None

    def load_rss_info(self, parsed: feedparser.FeedParserDict) -> None:
        """
        Load some RSS subscription elements into this feed state."""
        self.entries = []
        for entry in parsed.get("entries"):
            new_entry = {}
            new_entry["title"] = entry["title"]

            new_entry["urls"] = []
            new_entry["metadata"] = {}
            for enclosure in entry["enclosures"]:
                new_entry["urls"].append(enclosure["href"])

            self.entries.append(new_entry)

    def as_dict(self) -> Dict[str, Any]:
        """
        Return dictionary of this feed state object.

        :returns: Dictionary of this object's state.
        """

        return {"entries": self.entries,
                "entries_state_dict": self.entries_state_dict,
                "queue": list(self.queue),
                "latest_entry_number": self.latest_entry_number,
                "summary_queue": list(self.summary_queue),
                "last_modified": None,
                "etag": self.etag,
               }

    def store_last_modified(self, last_modified: Any) -> None:
        """
        Store last_modified as a datetime.

        :param last_modified: Last-modified time as time.struct_time.
        """
        if isinstance(last_modified, time.struct_time):
            LOG.debug("Updated last_modified.")
            self.last_modified = datetime.datetime.fromtimestamp(time.mktime(last_modified))
        else:
            LOG.debug("Unhandled 'last_modified' type, ignoring.")
            self.last_modified = None

    def __str__(self) -> str:
        return str(self.as_dict())

    def __repr__(self) -> str:
        return str(self)


# "Private" file functions (messy internals).
def _process_directory(d: Optional[str]) -> str:
    """Assign directory if none was given, and create directory if necessary."""
    if d is None:
        LOG.debug(f"No directory provided, creating a default one.")
        return util.expand(constants.APPDIRS.user_data_dir)

    directory = util.expand(d)

    LOG.debug(f"Using directory {directory}.")

    util.ensure_dir(directory)

    return directory


def _filter_nums(*, nums: List[int], min_lim: int=0, max_lim: int) -> List[int]:
    """Given two limits, remove elements from the list that aren't in that range."""
    return [num for num in nums if num > min_lim and num <= max_lim]

def _generate_feedparser(name: str) -> Any:
    """Perform rate-limited parse with feedparser."""

    @util.rate_limited(120, name)
    def _rate_limited_parser(url: str, etag: str, last_modified: Any) -> feedparser.FeedParserDict:
        # pylint: disable=no-member
        return feedparser.parse(url, etag=etag, modified=last_modified)

    return _rate_limited_parser


class UpdateResult(enum.Enum):
    """Enum describing possible results of trying to update a subscription."""
    SUCCESS = 0
    UNNEEDED = -1
    FAILURE = -2
    ATTEMPT_AGAIN = -3
