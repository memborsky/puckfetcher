import copy
import os
import urllib

import feedparser

import puckfetcher.error as PE
import puckfetcher.util as U

MAX_RECURSIVE_ATTEMPTS = 10

# TODO Switch to some kind of proper log library.
# TODO clean up prints to not have weird gaps.


# TODO describe field members, function parameters in docstrings.
class Subscription():
    """Object describing a podcast subscription."""

    # TODO Specify production vs test properly, somehow.
    def __init__(self, url=None, name=None, directory=None, download_backlog=True,
                 backlog_limit=None, production=True):

        self.production=production

        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if (url is None or url == ""):
            raise PE.MalformedSubscriptionError("No URL provided.")
        else:
            self.provided_url = copy.deepcopy(url)
            self.current_url = copy.deepcopy(url)

        # Maintain name of podcast.
        if (name is None or name == ""):
            raise PE.MalformedSubscriptionError("No name provided.")
        else:
            self.name = name

        # Save feed so we can retrieve multiple entries without retrieving it again.
        # Maintain old feed so we can
        # TODO allow multiple downloads at once.
        self.feed = None
        self.old_feed = None

        if directory is None:
            self.directory = U.get_xdg_data_dir_path(__package__, self.name)

            if not os.path.isdir(self.directory):
                os.makedirs(self.directory)
        else:
            self.directory = directory

        self.download_backlog = download_backlog
        if download_backlog:
            self.backlog_limit = backlog_limit

        else:
            self.get_feed()

        # Set a custom user agent.
        # TODO include version properly
        # TODO pull url from setup.py or something
        feedparser.USER_AGENT = __package__ + \
            "/Alpha +https://github.com/andrewmichaud/puckfetcher"

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
            print("""Too many recursive attempts ({0}) to get feed text for subscription
                   {1}, cancelling.""".format(attempt_count, self.name))
            raise PE.UnreachableFeedError(desc="Too many attempts needed to reach feed.")

        if self.current_url is None or self.current_url == "":
            print("""URL is empty or None, cannot get feed text for subscription
             {0}""".format(self.name))
            raise PE.MalformedSubscriptionError(desc="No URL after construction of subscription.")

        print("""Attempting to get feed text (attempt {0}) for subscription {1}
         with URL {2}.""".format(attempt_count, self.name, self.current_url))

        parsed = feedparser.parse(self.current_url)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status
        if status == 301:
            print("Permanent redirect to {0}.".format(parsed.href))
            print("Changing stored URL {0} for {1} to {2}.".format(self.current_url, self.name,
                                                                   parsed.href))
            self.current_url = parsed.href

            print("Attempting get with new URL {0}.".format(parsed.href))
            return self.get_feed_helper(attempt_count+1)

        elif status == 302:
            print("Temporary Redirect, attempting with new URL {0}.".format(parsed.href))
            print("Stored URL {0} for {1} will be unchanged.".format(self.current_url, self.name))

            old_url = self.current_url
            self.current_url = parsed.href
            result = self.get_feed_helper(attempt_count+1)
            self.current_url = old_url

            return result

        elif status == 404:
            print("""Page not found at {0}! Unable to retrieve feed text for
             {1}.""".format(self.current_url, self.name))
            print("Current URL will be preserved and checked again on next attempt.")
            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        elif status == 410:
            print("""Saw 410 - Gone at {0}. Unable to retrieve feed text for
             {1}.""".format(self.current_url, self.name))
            print("Clearing stored URL {0}.".format(self.current_url))
            print("""Originally provided URL {0} will be preserved, but no longer
             used.""".format(self.provided_url))
            print("Please provide new URL for subscription {0}.".format(self.name))
            self.current_url = None

            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        # TODO hook for dealing with password-protected feeds.
        elif status == 401:
            print("""Saw 401 - Forbidden at {0}. Unable to retrieve feed text for
             {1}.""".format(self.current_url, self.name))
            return None

        elif status != 200:
            print("""Saw non-200 status {0}. Attempting retrieve for feed text for URL
             {1} anyways.""".format(status, self.name, self.current_url))
            return self.get_feed_helper(attempt_count+1)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        print("status: {0}".format(parsed.status))
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            print("""Bozo exception! Unable to retrieve feed text for URL
             {0}.""".format(self.current_url))
            raise PE.MalformedFeedError("Malformed Feed", msg)

        # If we didn't detect any errors, we can save the feed.
        # However, only save the feed if it is different than the saved feed.
        # Return a boolean showing whether we changed the saved feed or not.
        if self.feed is None or self.feed != parsed:
            print("New feed is different than current feed, saving.")
            self.old_feed = copy.deepcopy(self.feed)
            self.feed = parsed
            return True

        else:
            print("New feed is identical to saved feed, not changing it.")
            return False

    # TODO provide a way to skip rate-limiting in dev mode.
    def get_feed(self):
        """Get RSS structure for this subscription. Return None if an error occurs."""
        return self.get_feed_helper(attempt_count=0)

    def download_entry_files(self, entry_age=0):
        """Download feed enclosure(s) to object directory."""

        directory = self.directory
        if entry_age < 0 or entry_age > len(self.feed["entries"]):
            print("Invalid entry age {0}.".format(entry_age))

        entry = self.feed["entries"][entry_age]
        enclosures = entry.enclosures
        print("Retrieved {0} enclosures for entry with age {1}.".format(len(enclosures),
                                                                        entry_age))

        # Create directory just for enclosures for this entry if there are many.
        if len(enclosures) > 1:
            directory = os.path.join(directory, entry.title)
            print("""More than 1 enclosure, creating directory {0} to house
             enclosures.""".format(directory))

        # TODO Check directory permissions.
        print("Working with directory {0}.".format(directory))
        if not os.path.isdir(directory):
            print("Creating directory {0}.".format(directory))
            os.makedirs(directory)

        for elem in range(len(enclosures)):
            print("Handling enclosure {0} of {1}.".format(elem+1, len(enclosures)))
            url = enclosures[elem].href
            print("Extracted url {0}.".format(url))
            filename = url.split('/')[-1]

            file_location = os.path.join(directory, filename)
            # If there is a file with the name we intend to save to, assume the podcast has been
            # downloaded already.
            if not os.path.exists(file_location):
                print("Saving file for enclosure {0} to {1}.".format(elem+1, file_location))
                urllib.request.urlretrieve(url, file_location)
            else:
                print("""File {0} already exists, assuming already downloaded and not
                 overwriting.""".format(file_location))

    def attempt_update(self):
        """Attempt to download new podcasts for a subscription."""

        # Check how many entries we've missed.
        print("Current feed: {0}.".format(self.feed))
        print("Old feed: {0}.".format(self.old_feed))

        # TODO attempt to clean up this logic.
        if self.feed is None or self.feed != self.old_feed:
            # Handle backlog if necessary.
            if self.feed is None:
                self.get_feed()

            if self.download_backlog:
                feed_len = len(self.feed["entries"])
                if self.backlog_limit is not None and self.backlog_limit < feed_len:
                    new_feeds_count = self.backlog_limit
                else:
                    new_feeds_count = feed_len

            else:

                # Get count of new feeds.
                if self.old_feed is None:
                    new_feeds_count = len(self.feed["entries"])
                else:
                    new_feeds_count = len(self.feed["entries"]) - len(self.old_feed["entries"])

            if new_feeds_count is None or new_feeds_count == 0:
                print("No new entries, no need to update.")
                return

            elif new_feeds_count < 0:
                print("Something bizarre has happened. Less than zero new feeds? Not updating.")
                return

            else:
                for i in reversed(range(0, new_feeds_count)):
                    print("Downloading entry with age {0}.".format(i))
                    self.download_entry_files(i)
        else:
            print("No new entries, no need to update.")
            return
