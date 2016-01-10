#!/usr/bin/env python3

import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import feedparser

import puckCatcher.puckError as PE

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
    print("directory: ", directory)
    if not os.path.isdir(directory):
        os.mkdir(directory)
    os.chdir(directory)

    # TODO handle file existing.
    for elem in enclosures:
        url = elem.href
        filename = url.split('/')[-1]
        print("attempting to save: ", url)
        print("to: ", os.path.join(directory, filename))
        urllib.request.urlretrieve(url, os.path.join(directory, filename))


def getLatestEntry(feedUrl):
    """Get latest entry from a feed."""
    parsed = feedparser.parse(feedUrl)

    # Detect bozo errors (malformed RSS/ATOM feeds).
    if parsed['bozo'] == 1:
        msg = parsed['bozo_exception'].getMessage()
        print("Bozo exception!", msg)
        raise PE.MalformedFeedError("Malformed Feed", msg)

    status = parsed.status
    if status == 301:
        print("Permanent Redirect! It's rude to keep using this url!")
        # TODO Have some mechanism to not check this URL again.
        return None
    elif status == 302:
        print("Temporary Redirect, nothing to do.")
    elif status == 404:
        print("Not found! Check url!")
        # TODO Have some mechanism to figure out this URL.
        return None
    elif status == 410:
        print("Gone! It's rude to keep using this url!")
        # TODO Have some mechanism to not check this URL again.
        return None
    elif status != 200:
        print("Something has gone wrong, better check that url!")
        # TODO Have some catch-all for everything that isn't OK.
        return None

    entries = parsed['entries']

    return entries[0]


def main():
    # TODO some semblance of argument parsing.
    for arg in sys.argv:
        print(arg)
    url = sys.argv[1]

    # TODO malformed URL check
    print("url: ", url)
    latestEntry = getLatestEntry(url)
    print("latest: ", latestEntry)
    print("latest title: ", latestEntry['title'])

    enclosures = latestEntry.enclosures
    print("Number of enclosures: ", len(enclosures))
    print("First (only?) enclosure: ", enclosures[0])
    print("Enclosure URL: ", enclosures[0].href)

    directory = os.path.join(ROOT, "foo")

    downloadFeedFiles(latestEntry, directory)

if __name__ == "__main__":
    main()
