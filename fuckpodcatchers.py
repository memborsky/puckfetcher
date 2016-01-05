import os
import sys
import urllib

import feedparser

# TODO xdg base directory support.
ROOT = os.path.dirname(os.path.realpath(__file__))


def downloadFeedFiles(entry, directory=ROOT):
    """
    Download feed enclosure(s) to specified directory, or ROOT if no directory
    specified.
    """

    enclosures = entry.enclosures

    # Create directory just for enclosures for this entry if there are many.
    if len(enclosures) > 1:
        directory = os.path.join(directory, entry.title)
        os.mkdir(directory)

    # TODO Check directory permissions.
    # TODO verbose time output.
    print "directory: ", directory
    if not os.path.isdir(directory):
        os.mkdir(directory)
    os.chdir(directory)

    # TODO handle file existing.
    for elem in enclosures:
        url = elem.href
        filename = url.split('/')[-1]
        print "attempting to save: ", url
        print "to: ", os.path.join(directory, filename)
        urllib.urlretrieve(url, os.path.join(directory, filename))


def checkIsLatestEntry(feedUrl, entryDict):
    """
    Given a dictionary, check if it represents the latest entry.  Because this
    requires downloading a new entry, return the latest entry if what we were
    given was not the latest entry.
    Return None otherwise.
    """
    latestEntry = getLatestEntry(feedUrl)
    if entryDict is not None and isinstance(entryDict, dict):
        if entryDict == latestEntry:
            return None

    return latestEntry


def getLatestEntry(feedUrl):
    """Get latest entry from a feed."""
    parsed = feedparser.parse(feedUrl)
    entries = parsed['entries']

    return entries[0]


def main():
    # TODO some semblance of argument parsing.
    for arg in sys.argv:
        print arg
    url = sys.argv[1]
    # TODO malformed URL check
    print "url: ", url
    latestEntry = getLatestEntry(url)
    print "latest: ", latestEntry
    print "latest title: ", latestEntry['title']

    enclosures = latestEntry.enclosures
    print "Number of enclosures: ", len(enclosures)
    print "First (only?) enclosure: ", enclosures[0]
    print "Enclosure URL: ", enclosures[0].href

    directory = os.path.join(ROOT, "foo")

    downloadFeedFiles(latestEntry, directory)

if __name__ == "__main__":
    main()
