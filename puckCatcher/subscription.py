import feedparser

import puckCatcher.puckError as PE

MAX_RECURSIVE_ATTEMPTS = 10

# TODO Switch to some kind of proper log library.

class Subscription():
    """
    Object describing a podcast subscription.
    """
    def __init__(self, url=None, name="", days=["ALL"], checkEvery="1 hour"):
        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        self.providedUrl = url
        self.currentUrl = url

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

        self.checkEvery = checkEvery

    def getLatestEntryHelper(self, count):
        """
           Helper method to get latest entry that can be called recursively.  Limited to
           MAX_RECURSIVE_ATTEMPTS attempts.
        """
        if count > MAX_RECURSIVE_ATTEMPTS:
            print("Too many recursive attempts ({0}) to get the latest entry for {1}, \
                  cancelling.".format(count, self.name))
            return None

        print("Attempting to get latest entry (attempt {0}) for {1}".format(count, self.name))

        parsed = feedparser.parse(self.currentUrl)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            print("Bozo exception!", msg)
            raise PE.MalformedFeedError("Malformed Feed", msg)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status
        if status == 301:
            print("Permanent redirect to {0}.".format(parsed.href))
            print("Changing stored URL {0} for {1} to {2}.".format(self.currentUrl, self.name,
                                                                   parsed.href))
            self.currentUrl = parsed.href

            print("Attempting get with new URL {1}.".format(parsed.href))
            return getLatestEntryHelper(count+1)

        elif status == 302:
            print("Temporary Redirect, attempting with new URL {0}.".format(parsed.href))
            print("Stored URL {0} for {1} will be unchanged.".format(self.currentUrl, self.name))

            oldUrl = self.currentUrl
            self.currentUrl = status.href
            result = getLatestEntryHelper(count+1)
            self.currentUrl = oldUrl

            return result

        elif status == 404:
            print("Page not found at {0}! Unable to retrieve latest entry for \
                  {0}.".format(self.currentUrl, self.name))
            print("Current URL will be preserved and checked again on next attempt.")
            return None

        elif status == 410:

            print("Saw 410 - Gone at {0}. Unable to retrieve latest entry for \
                  {1}.".format(self.currentUrl, self.name))
            print("Clearing stored URL {0}.".format(self.currentUrl))
            print("Originally provided URL {0} will be preserved, but not \
                  used.".format(self.providedUrl))
            print("Please provide new URL for subscription {0}.".format(self.name))
            self.currentUrl = parsed.href

            return None

        elif status != 200:
            print("Saw {0}. Attempting retrieve for {1} with URL {2} again.".format(status,
                                                                                    self.name,
                                                                                    self.currentUrl))
            return getLatestEntryHelper(count+1)

        # No errors detected, continue with fetching latest entry.
        return parsed['entries'][0]

    def getLatestEntry(self):
        """Get latest entry for this subscription. Return None if an error occurs."""
        self.getLatestEntryHelper(0)
