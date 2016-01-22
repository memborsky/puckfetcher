import datetime
import os
import urllib

import feedparser

import puckCatcher.puckError as PE

MAX_RECURSIVE_ATTEMPTS = 10

# TODO XDG defaults
DEFAULT_ROOT = "~/downloads"

# TODO Switch to some kind of proper log library.


# TODO describe field members, function parameters in docstrings.
class Subscription():
    """
    Object describing a podcast subscription.
    """
    def __init__(self, url=None, name="", days=["ALL"], checkEvery="1 hour"):
        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if (url is None or url == ""):
            raise PE.MalformedFeedError("Malformed Feed", "No URL provided")

        self.providedUrl = url
        self.currentUrl = url

        # Entry we currently care about. Either the latest entry, or a historical entry if we are
        # trying to catch up.
        self.entry = None

        # Maintain name of podcast.
        self.name = name

        # Attempt to parse date array. It will be stored internally as a list
        # of seven bools, to show whether we should look for a podcast on that
        # day. Weeks start on a Monday.

        # Allow either a string (Tuesday) or integer (2) day.
        uniqueDays = set(days)
        internalDays = [False] * 7
        # TODO should probably loudly fail if we can't parse.
        for day in uniqueDays:

            # Allow integer for day of week.
            if isinstance(day, int):
                if day < 1 or day > 7:
                    pass
                else:
                    internalDays[day-1] = True

            # Allow three-letter abbreviations, or full names.
            elif isinstance(day, str):
                lowerDay = day.lower()

                # User can put in 'monblarg', 'wedgargl', etc. if they want.
                if lowerDay.startswith("mon"):
                    internalDays[0] = True
                elif lowerDay.startswith("tue"):
                    internalDays[1] = True
                elif lowerDay.startswith("wed"):
                    internalDays[2] = True
                elif lowerDay.startswith("thur"):
                    internalDays[3] = True
                elif lowerDay.startswith("fri"):
                    internalDays[4] = True
                elif lowerDay.startswith("sat"):
                    internalDays[5] = True
                elif lowerDay.startswith("sun"):
                    internalDays[6] = True

        self.days = internalDays
        self.check = days

        # We start checking this podcast today. Do not check days before today even if there should
        # have been a podcast on those days.
        # TODO test
        self.today = datetime.now()
        if self.today.isoweekday() > 0:
            for elem in xrange(0, self.today.isoweekday()):
                if self.check[elem]:
                    self.check[elem] = False

        self.checkEvery = checkEvery

        # Set a custom user agent.
        # TODO include version properly
        feedparser.USER_AGENT = "PuckCatcher/Alpha " + \
                                "+https://github.com/andrewmichaud/FuckPodcatchers"

    def getEntryHelper(self, entryAge, attemptCount):
        """
        Helper method to get entry that can be called recursively.  Limited to
        MAX_RECURSIVE_ATTEMPTS attempts.
        """

        # TODO We should return a reason/error along with None.
        # Then testing can be stricter.
        if attemptCount > MAX_RECURSIVE_ATTEMPTS:
            print("Too many recursive attempts ({0}) to get entry with age {1} for subcription " +
                  "{2}, cancelling.".format(attemptCount, entryAge, self.name))
            return None

        if self.currentUrl is None or self.currentUrl == "":
            print("URL is empty or None, cannot get entry with age {0} for subscription " +
                  "{1}".format(entryAge, self.name))
            return None

        if not isinstance(entryAge, int) or entryAge < 0:
            print("Invalid entry age {0}.".format(entryAge))
            return None

        print("Attempting to get entry with age {0} (attempt {1}) for subscription {2} " +
              "with URL {3}.".format(entryAge, attemptCount, self.name, self.currentUrl))

        parsed = feedparser.parse(self.currentUrl)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status
        if status == 301:
            print("Permanent redirect to {0}.".format(parsed.href))
            print("Changing stored URL {0} for {1} to {2}.".format(self.currentUrl, self.name,
                                                                   parsed.href))
            self.currentUrl = parsed.href

            print("Attempting get with new URL {0}.".format(parsed.href))
            return self.getEntryHelper(entryAge, attemptCount+1)

        elif status == 302:
            print("Temporary Redirect, attempting with new URL {0}.".format(parsed.href))
            print("Stored URL {0} for {1} will be unchanged.".format(self.currentUrl, self.name))

            oldUrl = self.currentUrl
            self.currentUrl = parsed.href
            result = self.getEntryHelper(entryAge, attemptCount+1)
            self.currentUrl = oldUrl

            return result

        elif status == 404:
            print("Page not found at {0}! Unable to retrieve entry with age {1} for " +
                  "{2}.".format(self.currentUrl, entryAge, self.name))
            print("Current URL will be preserved and checked again on next attempt.")
            return None

        elif status == 410:
            print("Saw 410 - Gone at {0}. Unable to retrieve entry with age {1} for " +
                  "{2}.".format(self.currentUrl, entryAge, self.name))
            print("Clearing stored URL {0}.".format(self.currentUrl))
            print("Originally provided URL {0} will be preserved, but no longer " +
                  "used.".format(self.providedUrl))
            print("Please provide new URL for subscription {0}.".format(self.name))
            self.currentUrl = None

            return None

        elif status != 200:
            print("Saw non-200 status {0}. Attempting retrieve for entry with age {1} with URL " +
                  "{2} anyways.".format(status, self.name, self.currentUrl))
            return self.getEntryHelper(entryAge, attemptCount+1)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        print("status: {0}".format(parsed.status))
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            print("Bozo exception! Unable to retrieve entry with age {0} with URL " +
                  "{1}.".format(entryAge, self.currentUrl))
            raise PE.MalformedFeedError("Malformed Feed", msg)

        # See if the entry we want exists, or if there are not enough entries present.
        entryCount = len(parsed['entries'])
        if entryCount < entryAge + 1:
            print("There are only {0} entries at URL {1}: entry with age {2} does not " +
                  "exist.".format(entryCount, entryAge, self.currentUrl))
            return None

        # No errors detected, return entry. What an adventure.
        return parsed['entries'][entryAge]

    def getEntry(self, entryAge):
        """
        Get entry for this subscription. 0 is the newest entry and every higher number is one
        entry older than that. Return None if an error occurs.
        """
        return self.getEntryHelper(entryAge=entryAge, attemptCount=0)

    def downloadFeedFiles(self, directory=None):
        """
        Download feed enclosure(s) to specified directory, or ROOT if no directory is specified.
        """

        if directory is None:
            directory = os.path.join(DEFAULT_ROOT, self.name)
            print("Given no directory, defaulting to {0}.".format(directory))

        enclosures = self.entry.enclosures
        print("Retrieved {0} enclosures for the latest entry.".format(len(enclosures)))

        # Create directory just for enclosures for this entry if there are many.
        if len(enclosures) > 1:
            directory = os.path.join(directory, self.entry.title)
            print("More than 1 enclosure, creating directory {0} to house \
                  enclosures.".format(directory))

        # TODO Check directory permissions.
        # TODO verbose output.
        print("Working with directory {0}.".format(directory))
        if not os.path.isdir(directory):
            print("Creating directory {0}.".format(directory))
            os.mkdir(directory)
        os.chdir(directory)

        for elem in xrange(len(enclosures)):
            print("Handling enclosure {0} of {1}.".format(elem, len(enclosures)))
            url = elem.href
            print("Extracted url {0}.".format(url))
            filename = url.split('/')[-1]

            fileLocation = os.path.join(directory, filename)
            # If there is a file with the name we intend to save to, assume the podcast has been
            # downloaded already.
            if not os.path.exists(fileLocation):
                print("Saving file for enclosure {0} to {1}.".format(elem, fileLocation))
                urllib.request.urlretrieve(url, fileLocation)
            else:
                print("file {0} already exists, assuming already downloaded and not \
                      overwriting.".format(fileLocation))
