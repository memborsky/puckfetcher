# puckfetcher
[![BSD3 License](http://img.shields.io/badge/license-BSD3-brightgreen.svg)](https://tldrlegal.com/license/bsd-3-clause-license-%28revised%29)
[![Build Status](https://travis-ci.org/andrewmichaud/puckfetcher.svg?branch=master)](https://travis-ci.org/andrewmichaud/puckfetcher)
[![Coverage Status](https://coveralls.io/repos/andrewmichaud/puckfetcher/badge.svg?branch=master&service=github)](https://coveralls.io/github/andrewmichaud/puckfetcher?branch=master)
[![Issue Count](https://codeclimate.com/github/andrewmichaud/puckfetcher/badges/issue_count.svg)](https://codeclimate.com/github/andrewmichaud/puckfetcher)

a podcatcher that will finally work (for me)

hi

You're free to download and use this now. It should support Python 2.7, 3.4, and 3.5.

Build + Install:
```
python setup.py install
```

Test:
```
python setup.py test
```

This should be on PyPI and maybe other places soon.

## Complete

- Retrieve podcast feed.
- Get podcast file URL from feed.
- Download podcast file.
- Download a set number of podcasts from a feed's backlog.
- Detect number of feeds a podcast is behind based on last downloaded.
- Load settings from a file to determine which podcasts to download.
- Save settings to a cache to restore on application load.
- Intelligently merge user settings and application cache.
- Add script entry point to repeatedly update subscriptions.

## Before release
- ~100% test coverage
- lower code climate issues
- Git signing?
- PyPI release

## Future releases
- Add MP3 tag support to clean up tags based on feed information if it's messy.
- Clean up at least filenames based on feed title.
- Use etags/last-modified header to skip downloading feeds if we already have the latest feed.
- Attempt to support Jython/PyPy/IronPython/3.4/3.3
- Investigate Python static typing with https://docs.python.org/dev/library/typing.html#module-typing and mypy.

