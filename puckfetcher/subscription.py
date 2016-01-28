import copy
import datetime
import os
import urllib

import feedparser

import puckfetcher.error as PE
import puckfetcher.util as U

MAX_RECURSIVE_ATTEMPTS = 10

# TODO XDG defaults
DEFAULT_ROOT = os.path.join(os.getcwd(), "store")

# TODO Switch to some kind of proper log library.
# TODO clean up prints to not have weird gaps.


# TODO describe field members, function parameters in docstrings.
class Subscription():
    """
    Object describing a podcast subscription.
    """

    def __init__(self, url=None, name="", days=["ALL"]):
        # Maintain separate data members for originally provided URL and URL we may develop due to
        # redirects.
        if (url is None or url == ""):
            raise PE.MalformedSubscriptionError("No URL provided.")

        self.providedUrl = copy.deepcopy(url)
        self.currentUrl = copy.deepcopy(url)

        # Save feed so we can retrieve multiple entries without retrieving it again.
        # TODO allow multiple downloads at once.
        self.feed = None

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

        self.days = copy.deepcopy(internalDays)

        self.today = datetime.datetime.now().date()

        # Set a custom user agent.
        # TODO include version properly
        feedparser.USER_AGENT = "PuckCatcher/Alpha " + \
                                "+https://github.com/andrewmichaud/FuckPodcatchers"

    def getFeedHelper(self, attemptCount):
        """
        Helper method to get feed text that can be called recursively. Limited to
        MAX_RECURSIVE_ATTEMPTS attempts.
        """

        # TODO We should return a reason/error along with None.
        # Then testing can be stricter.
        if attemptCount > MAX_RECURSIVE_ATTEMPTS:
            print("Too many recursive attempts ({0}) to get feed text for subscription " +
                  "{1}, cancelling.".format(attemptCount, self.name))
            raise PE.UnreachableFeedError(desc="Too many attempts needed to reach feed.")

        if self.currentUrl is None or self.currentUrl == "":
            print("URL is empty or None, cannot get feed text for subscription " +
                  "{0}".format(self.name))
            raise PE.MalformedSubscriptionError(desc="No URL after construction of subscription.")

        print("""Attempting to get feed text (attempt {0}) for subscription {1}
              with URL {2}.""".format(attemptCount, self.name, self.currentUrl))

        parsed = feedparser.parse(self.currentUrl)

        # Detect some kinds of HTTP status codes signalling failure.
        status = parsed.status
        if status == 301:
            print("Permanent redirect to {0}.".format(parsed.href))
            print("Changing stored URL {0} for {1} to {2}.".format(self.currentUrl, self.name,
                                                                   parsed.href))
            self.currentUrl = parsed.href

            print("Attempting get with new URL {0}.".format(parsed.href))
            return self.getFeedHelper(attemptCount+1)

        elif status == 302:
            print("Temporary Redirect, attempting with new URL {0}.".format(parsed.href))
            print("Stored URL {0} for {1} will be unchanged.".format(self.currentUrl, self.name))

            oldUrl = self.currentUrl
            self.currentUrl = parsed.href
            result = self.getFeedHelper(attemptCount+1)
            self.currentUrl = oldUrl

            return result

        elif status == 404:
            print("Page not found at {0}! Unable to retrieve feed text for " +
                  "{1}.".format(self.currentUrl, self.name))
            print("Current URL will be preserved and checked again on next attempt.")
            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        elif status == 410:
            print("Saw 410 - Gone at {0}. Unable to retrieve feed text for " +
                  "{1}.".format(self.currentUrl, self.name))
            print("Clearing stored URL {0}.".format(self.currentUrl))
            print("Originally provided URL {0} will be preserved, but no longer " +
                  "used.".format(self.providedUrl))
            print("Please provide new URL for subscription {0}.".format(self.name))
            self.currentUrl = None

            raise PE.UnreachableFeedError(desc="Unable to retrieve feed.", code=status)

        # TODO hook for dealing with password-protected feeds.
        elif status == 401:
            print("""Saw 401 - Forbidden at {0}. Unable to retrieve feed text for
                  {1}.""".format(self.currentUrl, self.name))
            return None

        elif status != 200:
            print("Saw non-200 status {0}. Attempting retrieve for feed text for URL " +
                  "{1} anyways.".format(status, self.name, self.currentUrl))
            return self.getFeedHelper(attemptCount+1)

        # Detect bozo errors (malformed RSS/ATOM feeds).
        print("status: {0}".format(parsed.status))
        if parsed['bozo'] == 1:
            msg = parsed['bozo_exception'].getMessage()
            print("Bozo exception! Unable to retrieve feed text for URL " +
                  "{0}.".format(self.currentUrl))
            raise PE.MalformedFeedError("Malformed Feed", msg)

        # If we didn't detect any errors, we can save the feed.
        # However, only save the feed if it is different than the saved feed.
        # Return a boolean showing whether we changed the saved feed or not.
        if self.feed is None:
            print("No existing feed, saving.")
            self.feed = parsed
            return True

        elif self.feed != parsed:
            print("New feed is different than current feed, saving.")
            self.feed = parsed
            return True

        else:
            print("New feed is identical to saved feed, not changing it.")
            return False

    # TODO provide a way to skip rate-limiting for my sites while testing (not in production).
    @U.RateLimited(60)
    def getFeed(self):
        """Get RSS structure for this subscription. Return None if an error occurs."""
        return self.getFeedHelper(attemptCount=0)

    @U.RateLimited(30)
    def downloadEntryFiles(self, entryAge=0, directory=None):
        """
        Download feed enclosure(s) to specified directory, or DEFAULT_ROOT if no directory is
        specified.
        """

        if directory is None:
            directory = os.path.join(DEFAULT_ROOT, self.name)
            print("Given no directory, defaulting to {0}.".format(directory))

        if entryAge < 0 or entryAge > len(self.feed["entries"]):
            print("Invalid entry age {0}.".format(entryAge))

        entry = self.feed["entries"][entryAge]
        enclosures = entry.enclosures
        print("Retrieved {0} enclosures for the latest entry.".format(len(enclosures)))

        # Create directory just for enclosures for this entry if there are many.
        if len(enclosures) > 1:
            directory = os.path.join(directory, entry.title)
            print("More than 1 enclosure, creating directory {0} to house \
                  enclosures.".format(directory))

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

            fileLocation = os.path.join(directory, filename)
            # If there is a file with the name we intend to save to, assume the podcast has been
            # downloaded already.
            if not os.path.exists(fileLocation):
                print("Saving file for enclosure {0} to {1}.".format(elem+1, fileLocation))
                urllib.request.urlretrieve(url, fileLocation)
            else:
                print("file {0} already exists, assuming already downloaded and not \
                      overwriting.".format(fileLocation))

    def attemptUpdate(self):
        """Attempt to download new podcasts for a subscription."""

        # Detect how far we've drifted from the correct current date.
        # This lets us estimate how many podcasts we should download.
        currentToday = datetime.datetime.now().date()
        offset = currentToday - self.today
        oneDelta = datetime.timedelta(1)
        newDate = currentToday + oneDelta
        print("Stored date: {0}.".format(self.today))
        print("Current date: {0}.".format(currentToday))
        print("Difference: {0}.".format(offset))

        if offset.days < 0:
            print("Stored date is ahead of the actual current date.")
            print("Doing nothing until it catches up.")
            return

        elif offset.days == 0:
            print("Dates match, checking if we should download.")
            if self.days[self.today.isoweekday()-1]:
                print("Triggering download.")
                feedChanged = self.getFeed()
                if (feedChanged):
                    self.downloadEntryFiles(0)
                else:
                    print("Stored feed not changed, not downloading anything.")

        elif (offset.days > 0):
            print("Stored date is behind the actual current date.")

            # Check if there have been new podcasts, so we know if we should bother downloading
            # anything.
            print("Retrieving feed for subscription {0}.".format(self.name))
            feedUpdated = self.getFeed()

            if not feedUpdated:
                print("Feed not updated, not bothering to download anything.")
                return

            # TODO if an rss feed doesn't have set days, we can't pull this neat(?) trick to see
            # how many podcasts to download. We'll just have to compare the feeds and see how many
            # entries have been added.
            # Determine how many of the days we're behind are days where we would want to check for
            # a podcast.

            missed = 0
            dayBuckets = [0]*7

            # If the offset is small enough, just go through every day and record what days of the
            # week we missed.
            if (offset.days <= 7):
                print("Offset ({0}), less than 7.".format(offset))
                for i in range(offset.days):
                    index = (self.today + datetime.timedelta(i)).isoweekday()
                    print("Incrementing bucket {0}.".format(i))
                    dayBuckets[index-1] += 1

            # Otherwise, handle the weeks of self.today and currentToday like we did in the other
            # if case, and then just divide by 7 to figure out how many other days we missed.
            else:
                while self.today.isoweekday() < 7:
                    print("""Handling first week of offset. self.today is now
                          {0}.""".format(self.today))
                    print("Offset is now {0}.".format(offset))
                    print("Current ISO weekday is {0}.".format(self.today.isoweekday()))
                    dayBuckets[self.today.isoweekday()-1] += 1
                    self.today += oneDelta
                    offset -= oneDelta

                dayBuckets[self.today.isoweekday()-1] += 1
                offset -= oneDelta

                while currentToday.isoweekday() > 1:
                    print("Handling last week of offset. currentToday is now " +
                          "{0}.".format(currentToday))
                    print("Offset is now {0}.".format(offset))
                    print("Current ISO weekday is {0}.".format(currentToday.isoweekday()))
                    dayBuckets[currentToday.isoweekday()-1] += 1
                    currentToday -= oneDelta
                    offset -= oneDelta

                dayBuckets[currentToday.isoweekday()-1] += 1
                offset -= oneDelta

                perWeekdayPassed = offset / 7
                print("Incrementing every day by {0}.".format(perWeekdayPassed))
                for day in range(len(dayBuckets)):
                    dayBuckets[day] += perWeekdayPassed.days

            print("Final daybucket contents:")
            for day in range(len(dayBuckets)):
                print("daybucket {0} has {1}.".format(day, dayBuckets[day]))

            # Determine how many of the days that have passed would have had a podcast.
            for i in range(len(dayBuckets)):
                if self.days[i]:
                    missed += dayBuckets[i]

            print("Missed {0} podcasts for subscription {1}.".format(missed, self.name))

            for i in reversed(range(0, missed)):
                print("Downloading entry with age {0}.".format(i))
                self.downloadEntryFiles(i)

        print("Incrementing stored day from {0} to {1}.".format(self.today, self.today + oneDelta))
        self.today = newDate
        print("Stored day is {0}.".format(self.today))
