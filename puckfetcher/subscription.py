import copy
import logging
import os
import pkg_resources
import textwrap
import urllib
from urllib.request import FancyURLopener

import feedparser

import puckfetcher.error as PE
import puckfetcher.util as U

MAX_RECURSIVE_ATTEMPTS = 10
# TODO can we retrieve this only once?
VERSION = pkg_resources.require("puckfetcher")[0].version
USER_AGENT = __package__ + "/" + VERSION + " +https://github.com/andrewmichaud/puckfetcher"

logger = logging.getLogger("root")


class PuckURLOpener(FancyURLopener):
    version = USER_AGENT

urllib._urlopener = PuckURLOpener()


# TODO describe field members, function parameters in docstrings.
class Subscription():
    """Object describing a podcast subscription."""

    # TODO Specify production vs test properly, somehow.
    def __init__(self, url=None, name=None, directory=None, download_backlog=True,
                 backlog_limit=None, production=True):

        self.production = production
        logger.info("Running in production mode: {0}.".format(production))

        # This will be set on first update attempt.
        self.latest_entry_number = None

        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if (url is None or url == ""):
            raise PE.MalformedSubscriptionError("No URL provided.")
        else:
            logger.debug("Storing provided url {0}.".format(url))
            self.provided_url = copy.deepcopy(url)
            self.current_url = copy.deepcopy(url)

        # Maintain name of podcast.
        if (name is None or name == ""):
            raise PE.MalformedSubscriptionError("No name provided.")
        else:
            logger.debug("Provided name {0}.".format(name))
            self.name = name

        # Save feed so we can retrieve multiple entries without retrieving it again.
        # Maintain old feed so we can
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
        self.download_entry_files = U.rate_limited(self.production, 30,
                                                   self.name)(self.download_entry_files)

    def get_feed_helper(self, attempt_count):
        """
        Helper method to get feed text that can be called recursively. Limited to
        MAX_RECURSIVE_ATTEMPTS attempts.
        """

        # TODO We should return a reason/error along with None.
        # Then testing can be stricter.
        if attempt_count > MAX_RECURSIVE_ATTEMPTS:
            logger.error(textwrap.dedent(
                """
                Too many recursive attempts ({0}) to get feed for subscription {1}, cancelling.
                """.format(attempt_count, self.name)))
            raise PE.UnreachableFeedError(desc="Too many attempts needed to reach feed.")

        if self.current_url is None or self.current_url == "":
            logger.error(textwrap.dedent(
                """
                URL is empty or None, cannot get feed text for subscription {0}.
                """.format(self.name)))
            raise PE.MalformedSubscriptionError(desc="No URL after construction of subscription.")

        logger.error(textwrap.dedent(
            """
            Attempting to get feed text (attempt {0}) for subscription {1} with URL {2}.
            """.format(attempt_count, self.name, self.current_url)))

        parsed = feedparser.parse(self.current_url)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status
        if status == 301:
            logger.warning(textwrap.dedent(
                """
                Permanent redirect to {0}.
                Changing stored URL {0} for {1} to {2} and attempting get with new URL.
                """.format(parsed.href, self.current_url, self.name, parsed.href)))

            self.current_url = parsed.href
            return self.get_feed_helper(attempt_count+1)

        elif status == 302:
            logger.warning(textwrap.dedent(
                """
                Temporary Redirect, attempting with new URL {0}.
                Stored URL {0} for {1} will be unchanged.
                """.format(parsed.href, self.current_url, self.name)))

            old_url = self.current_url
            self.current_url = parsed.href
            result = self.get_feed_helper(attempt_count+1)
            self.current_url = old_url

            return result

        elif status == 404:
            logger.error(textwrap.dedent(
                """
                Page not found at {0}! Unable to retrieve feed text for {1}.
                Current URL {0} for {1} will be preserved and checked again on next attempt.
                """.format(self.current_url, self.name)))
            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        elif status == 410:
            logger.error(textwrap.dedent(
                """
                Saw 410 - Gone at {0}. Unable to retrieve feed text for {1}.
                Clearing stored URL {0} from current_url for {1}.
                Originally provided URL {0} will be maintained at provided_url, but will no longer
                be used.
                Please provide new URL for subscription {1}.
                """.format(self.current_url, self.name)))
            self.current_url = None
            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        # TODO hook for dealing with password-protected feeds.
        elif status == 401:
            logger.error(textwrap.dedent(
                """
                Saw 401 - Unauthorized at {0}. Unable to retrieve feed text for {1}.
                Clearing stored URL {0} from current_url for {1}.
                Originally provided URL {0} will be maintained at provided_url, but will no longer
                be used.
                Please provide new URL and authorization for subscription {1}.
                """.format(self.current_url, self.name)))
            self.current_url = None
            raise PE.UnreachableFeedError(desc="Unable to retrieve feed without authorization.",
                                          code=status)

        elif status != 200:
            logger.warning(textwrap.dedent(
                """
                Saw non-200 status {0}. Attempting feed retrieve with URL {1} for {2} anyways.
                """.format(status, self.current_url, self.name)))
            return self.get_feed_helper(attempt_count+1)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            logger.error(textwrap.dedent(
                """
                Received bozo exception {0}. Unable to retrieve feed with URL {1} for {2}.
                """.format(msg, self.current_url, self.name)))
            raise PE.MalformedFeedError("Malformed Feed", msg)

        # If we didn't detect any errors, we can save the feed.
        # However, only save the feed if it is different than the saved feed.
        # Return a boolean showing whether we changed the saved feed or not.
        if self.feed is None or self.feed != parsed:
            logger.info(textwrap.dedent(
                """
                New feed is different than current feed, saving it.
                """))
            self.old_feed = copy.deepcopy(self.feed)
            self.feed = parsed
            return True

        else:
            logger.info(textwrap.dedent(
                """
                New feed is identical to current feed, not saving it.
                """))
            return False

    def get_feed(self):
        """Get RSS structure for this subscription. Return None if an error occurs."""
        return self.get_feed_helper(attempt_count=0)

    def download_entry_files(self, entry_age=0):
        """Download feed enclosure(s) to object directory."""

        directory = self.directory
        if entry_age < 0 or entry_age > len(self.feed["entries"]):
            logger.error(textwrap.dedent(
                """
                Given invalid entry age {0} to download for {1}.
                """.format(entry_age, self.name)))
            return

        logger.info("Downloading entry {0} for {1}.".format(entry_age, self.name))

        entry = self.feed["entries"][entry_age]
        enclosures = entry.enclosures
        logger.info(textwrap.dedent(
            """
            There are {0} enclosures for entry with age {1}.
            """.format(len(enclosures), entry_age)))

        # Create directory just for enclosures for this entry if there are many.
        if len(enclosures) > 1:
            directory = U.get_and_make_directory_generic(directory, entry.title)
            logger.debug(textwrap.dedent(
                """
                More than 1 enclosure for entry {0}, creating directory {1} to store them.
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
                urllib.request.urlretrieve(url, file_location)
            else:
                logger.info(textwrap.dedent(
                    """
                    File {0} already exists, assuming already downloaded and not overwriting.
                    """.format(file_location)))

    def attempt_update(self):
        """Attempt to download new entries for a subscription."""

        # Check how many entries we've missed.
        # TODO attempt to clean up this logic.
        if self.feed is None:
            logger.error("No feed, cannot attempt update.")
            # TODO should throw some kind of error?
            return

        number_to_download = 0
        number_feeds = len(self.feed["entries"])
        if self.feed != self.old_feed:
            if self.latest_entry_number is None:
                if self.download_backlog:
                    if self.backlog_limit is None:
                        number_to_download = number_feeds
                        logger.info(textwrap.dedent(
                            """
                            Backlog limit for {0} is set to None.
                            Interpreting as "No Limit" and downloading full backlog ({1} entries).
                            """.format(self.name, number_to_download)))

                    elif self.backlog_limit < 0:
                        logger.error(textwrap.dedent(
                            """
                            Invalid backlog limit {0}, downloading nothing.
                            """.format(self.backlog_limit)))
                        return

                    elif self.backlog_limit <= number_feeds:
                        number_to_download = self.backlog_limit
                        logger.info(textwrap.dedent(
                            """
                            Backlog limit for {0} is set to {1}, less than number of feeds {2}.
                            Downloading {1} entries.
                            """.format(self.name, self.backlog_limit, number_feeds,
                                       number_to_download)))

                    else:
                        number_to_download = number_feeds
                        logger.info(textwrap.dedent(
                            """
                            Backlog limit for {0} is set to {1}, greater than number of feeds {2}.
                            Downloading only {1} entries.
                            """.format(self.name, self.backlog_limit, number_feeds,
                                       number_to_download)))

                else:
                    self.latest_entry_number = number_feeds
                    logger.info(textwrap.dedent(
                        """
                        Download backlog for {0} is not set.
                        Downloading nothing, but setting number downloaded to {1}.
                        """.format(self.name, self.latest_entry_number)))

            elif self.latest_entry_number < number_feeds:
                number_to_download = number_feeds - self.latest_entry_number
                logger.info(textwrap.dedent(
                    """
                    Number of downloaded feeds for {0} is {1}, {2} less than feed entry count {3}.
                    Downloading {1} entries.
                    """.format(self.name, self.latest_entry_number, number_to_download,
                               number_feeds)))

            else:
                logger.info(textwrap.dedent(
                    """
                    Number downloaded for {0} matches feed entry count {1}.
                    Nothing to download.
                    """.format(self.name, number_feeds)))
                return

        # Downloading feeds oldest first makes the most sense for RSS feeds (IMO), so we do that,
        # even if it requires a slight amount of extra work.
        for i in reversed(range(0, number_to_download)):
            logger.info("Downloading entry with age {0}.".format(i))
            self.download_entry_files(i)

            if self.latest_entry_number is None:
                self.latest_entry_number = 1
            else:
                self.latest_entry_number += 1
            logger.info(textwrap.dedent(
                """
                Have downloaded {0} entries for subscription {1}.
                """.format(self.latest_entry_number, self.name)))
