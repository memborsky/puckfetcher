import copy
import logging
import os
import pkg_resources
import textwrap

import feedparser
import requests

import puckfetcher.error as E
import puckfetcher.util as U

MAX_RECURSIVE_ATTEMPTS = 10
# TODO can we retrieve this only once?
VERSION = pkg_resources.require("puckfetcher")[0].version
USER_AGENT = "puckfetcher/" + VERSION + " +https://github.com/andrewmichaud/puckfetcher"

logger = logging.getLogger("root")


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

        # Save feed so we can retrieve multiple entries without retrieving it again.
        # Maintain old feed so we can tell if a new feed is different.
        # TODO allow multiple downloads at once.
        self.feed = None
        self.old_feed = None

        if directory is None:
            self.directory = U.get_xdg_data_dir_path(__package__, self.name)
            logger.debug("No directory provided, defaulting to {0}.".format(directory))

        else:
            self.directory = directory
            logger.debug("Provided directory {0}.".format(directory))

            if not os.path.isdir(self.directory):
                logger.debug("Directory {0} does not exist, creating it.".format(directory))
                os.makedirs(self.directory)

        self.download_backlog = download_backlog
        logger.debug("Set to download backlog: {0}.".format(download_backlog))

        self.backlog_limit = backlog_limit
        logger.debug("Backlog limit: {0}.".format(backlog_limit))

        # Set a custom user agent.
        # TODO pull url from setup.py or something
        feedparser.USER_AGENT = USER_AGENT
        logger.debug("User agent: {0}.".format(USER_AGENT))

        # Provide rate limiting.
        self.get_feed = U.rate_limited(self.production, 60, self.name)(self.get_feed)
        self.download_file = U.rate_limited(self.production, 30, self.name)(self.download_file)

    def _get_feed_helper(self, attempt_count):
        """
        Helper method to get feed text that can be called recursively. Limited to
        MAX_RECURSIVE_ATTEMPTS attempts.
        """

        # TODO We should return a reason/error along with None.
        # Then testing can be stricter.
        if attempt_count > MAX_RECURSIVE_ATTEMPTS:
            logger.error(textwrap.dedent(
                """\
                Too many recursive attempts ({0}) to get feed for subscription {1}, cancelling.\
                """.format(attempt_count, self.name)))
            raise E.UnreachableFeedError(desc="Too many attempts needed to reach feed.")

        if self._current_url is None or self._current_url == "":
            logger.error(textwrap.dedent(
                """\
                URL is empty or None, cannot get feed text for subscription {0}.\
                """.format(self.name)))
            raise E.MalformedSubscriptionError(desc="No URL after construction of subscription.")

        logger.info(textwrap.dedent(
            """\
            Attempting to get feed text (attempt {0}) for subscription {1} with URL {2}.\
            """.format(attempt_count, self.name, self._current_url)))

        parsed = feedparser.parse(self._current_url)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status

        # This is vaguely gross and doesn't handle the duplicates they have in requests.codes.
        rev = {v: k for k, v in requests.codes.__dict__.items()}
        if status == requests.codes.OK:
            logger.info("Saw {0} - {1} status.".format(status, rev[status]))
        else:
            logger.warning("Saw non-200 status {0} - {1}.".format(status, rev[status]))

        if status in [requests.codes.MOVED_PERMANENTLY, requests.codes.PERMANENT_REDIRECT]:
            logger.warning(textwrap.dedent(
                """\
                Changing stored URL {0} for {1} to {2} and attempting get with new URL.\
                """.format(self._current_url, self.name, parsed.href)))

            self._current_url = parsed.href
            return self._get_feed_helper(attempt_count+1)

        elif status in [requests.codes.FOUND,
                        requests.codes.SEE_OTHER,
                        requests.codes.TEMPORARY_REDIRECT]:
            logger.warning(textwrap.dedent(
                """\
                Attempting with new URL {0}. Stored URL {0} for {1} will be unchanged.\
                """.format(parsed.href, self._current_url, self.name)))

            old_url = self._current_url
            self._current_url = parsed.href
            result = self._get_feed_helper(attempt_count+1)
            self._current_url = old_url

            return result

        elif status == requests.codes.NOT_FOUND:
            logger.error(textwrap.dedent(
                """\
                Unable to retrieve feed text for {1}.
                Current URL {0} for {1} will be preserved and checked again on next attempt.\
                """.format(self._current_url, self.name)))
            raise E.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        # TODO hook for dealing with password-protected feeds.
        elif status in [requests.codes.UNAUTHORIZED, requests.codes.GONE]:
            logger.error(textwrap.dedent(
                """\
                Unable to retrieve feed text for {1}.
                Clearing stored URL {0} from _current_url for {1}.
                Originally provided URL {0} will be maintained at _provided_url, but will no longer
                be used.
                Please provide new URL and authorization for subscription {1}.\
                """.format(self._current_url, self.name)))
            self._current_url = None
            if status == requests.codes.UNAUTHORIZED:
                raise E.UnreachableFeedError(desc="Unable to retrieve feed without authorization.",
                                             code=status)
            else:
                raise E.UnreachableFeedError(desc="Unable to retrieve feed, feed is gone.",
                                             code=status)

        elif status != 200:
            logger.warning(textwrap.dedent(
                """\
                Saw unhandled non-200 status {0}. Attempting feed retrieve with URL {1} for {2}
                anyways.\
                """.format(status, self._current_url, self.name)))
            return self._get_feed_helper(attempt_count+1)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            logger.error(textwrap.dedent(
                """\
                Received bozo exception {0}. Unable to retrieve feed with URL {1} for {2}.\
                """.format(msg, self._current_url, self.name)))
            raise E.MalformedFeedError("Malformed Feed", msg)

        # If we didn't detect any errors, we can save the feed.
        # However, only save the feed if it is different than the saved feed.
        # Return a boolean showing whether we changed the saved feed or not.
        if self.feed is None or self.feed != parsed:
            logger.info("New feed is different than current feed, saving it.")
            self.old_feed = copy.deepcopy(self.feed)
            self.feed = copy.deepcopy(parsed)
            return True

        else:
            logger.info("New feed is identical to current feed, not saving it.")
            return False

    def get_feed(self, attempt_count=0):
        """Get RSS structure for this subscription. Return None if an error occurs."""
        return self._get_feed_helper(attempt_count=attempt_count)

    def download_entry_files(self, entry_age=0):
        """Download feed enclosure(s) to object directory."""

        directory = self.directory
        if entry_age < 0 or entry_age >= len(self.feed["entries"]):
            logger.error("Given invalid entry age {0} to download for {1}.".format(entry_age,
                                                                                   self.name))
            return

        logger.info("Downloading entry {0} for {1}.".format(entry_age, self.name))

        entry = self.feed["entries"][entry_age]
        enclosures = entry.enclosures
        logger.info("There are {0} enclosures for entry with age {1}.".format(len(enclosures),
                                                                              entry_age))

        # Create directory just for enclosures for this entry if there are many.
        if len(enclosures) > 1:
            directory = U.get_and_make_directory_generic(directory, entry.title)
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

            # If there is a file with the name we intend to save to, assume the podcast has been
            # downloaded already.
            if not os.path.exists(file_location):
                logger.info("Saving file for enclosure {0} to {1}.".format(i+1, file_location))
                self.download_file(url, file_location)

            else:
                logger.info(textwrap.dedent(
                    """\
                    File {0} already exists, assuming already downloaded and not overwriting.\
                    """.format(file_location)))

    def download_file(self, url, file_location):
        """Download a file. Wrapper around the *actual* write to allow targeted rate limiting."""
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers)
        with open(file_location, "wb") as f:
            f.write(response.content)

    def attempt_update(self):
        """Attempt to download new entries for a subscription."""

        self.get_feed()

        # Check how many entries we've missed.
        if self.feed is None:
            logger.error("No feed, cannot attempt update.")
            # TODO should throw some kind of error?
            return

        number_to_download = 0
        number_feeds = len(self.feed["entries"])
        # TODO I've cleaned up this logic before, but it's worth trying again.
        if self.feed != self.old_feed:
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
                        return

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
                return

        # Downloading feeds oldest first makes the most sense for RSS feeds (IMO), so we do that.
        for i in range(number_to_download, 0, -1):
            logger.info("Downloading entry with age {0}.".format(i))
            self.download_entry_files(i)

            self.latest_entry_number += 1
            logger.info(textwrap.dedent(
                """\
                Have downloaded {0} entries for subscription {1}.\
                """.format(self.latest_entry_number, self.name)))


def parse_from_user_yaml(sub_yaml):
    """Parse YAML user-provided subscription into a subscription object."""

    name = sub_yaml.get("name", "Generic Podcast")

    if sub_yaml["url"] is None:
        raise E.InvalidConfigError("No URL provided, URL is mandatory!")
    else:
        url = sub_yaml["url"]

    download_backlog = sub_yaml.get("download_backlog", True)
    backlog_limit = sub_yaml.get("backlog_limit", None)

    # TODO add ability to pretty-print subscription and print here.
    return Subscription(name=name, url=url, download_backlog=download_backlog,
                        backlog_limit=backlog_limit)


def dict_to_subscription(dictionary):
    """Parse a dictionary into a subscription."""
    sub = Subscription.__new__(Subscription)
    sub.latest_entry_number = dictionary["latest_entry_number"]
    sub._provided_url = dictionary["_provided_url"]
    sub._current_url = dictionary["_current_url"]
    sub.name = dictionary["name"]
    sub.feed = dictionary["feed"]
    sub.old_feed = dictionary["old_feed"]
    sub.directory = dictionary["directory"]
    sub.download_backlog = dictionary["download_backlog"]
    sub.backlog_limit = dictionary["backlog_limit"]
    return sub


def encode_subscription(obj):
    """Encode subscription as dictionary for msgpack."""
    if isinstance(obj, Subscription):
        return {"_subscription_": True,
                "latest_entry_number": obj.latest_entry_number,
                "_provided_url": obj._provided_url,
                "_current_url": obj._current_url,
                "name": obj.name,
                "feed": obj.feed,
                "old_feed": obj.old_feed,
                "directory": obj.directory,
                "download_backlog": obj.download_backlog,
                "backlog_limit": obj.backlog_limit}
    return obj


def decode_subscription(obj):
    """Decode subscription from msgpack binary object."""
    if b'_subscription_' in obj:
        name = obj[b"name"].decode("utf-8")
        url = obj[b"_provided_url"].decode("utf-8")
        sub = Subscription(url=url, name=name)

        sub.latest_entry_number = obj[b"latest_entry_number"]
        sub._current_url = obj[b"_current_url"].decode("utf-8")
        sub.name = obj[b"name"].decode("utf-8")
        sub.feed = obj[b"feed"]
        sub.old_feed = obj[b"old_feed"]
        sub.directory = obj[b"directory"].decode("utf-8")
        sub.download_backlog = obj[b"download_backlog"]
        sub.backlog_limit = obj[b"backlog_limit"]
        return sub
    return obj
