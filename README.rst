puckfetcher
===========

| |BSD3 License|
| |Build Status|
| |Coverage Status|
| |Issue Count|

a podcatcher that will finally work (for me)

Hello!

This should support Python 2.7, 3.3, 3.4, and 3.5. Feel free to report
any issues here, and I’ll investigate when/if I can.

| You’ll need setuptools (https://pypi.python.org/pypi/setuptools) to
  run this in its current state. Go get it, clone this repo, and you
| can run the below commands. Should work on OSX and Linux, from the
  command line. You’ll want a default config file, name it config.yaml
| and look at example\_config.yaml to see how it should be structured.

Directory for config file:

-  OSX: /Users/[USERNAME]/Application Support/puckfetcher/config.yaml
-  Linux: /home/[USERNAME]/.config/puckfetcher/config.yaml

Build + Install:

::

    python setup.py install

Test:

::

    python setup.py test

Complete
--------
-  Retrieve podcast feed.
-  Get podcast file URL from feed.
-  Download podcast file.
-  Download a set number of podcasts from a feed’s backlog.
-  Load settings from a file to determine which podcasts to download.
-  Save settings to a cache to restore on application load.
-  Intelligently merge user settings and application cache.
-  Add script entry point to repeatedly update subscriptions.
-  Use etags/last-modified header to skip downloading feeds if we
   already have the latest feed, to not waste bandwidth.
-  PyPI release!
-  Text-based progress for podcast downloads (via Clint).
-  Clean up subscriptions code and get Pylint to like it.

Current Tasks
-------------
-  Local file support for rss feeds.
-  lower code climate issues

Future releases
---------------
-  Text-based progress for other time-consuming actions.
-  Clean up at least filenames based on feed title.
-  Add MP3 tag support to clean up tags based on feed information if
   it’s messy.
-  Cut out more errors in favor of verbose logging, unless we absolutely can't keep running.
-  ncurses support/gui of some kind
-  Attempt to support Jython/PyPy/IronPython/3.4/3.3
-  Investigate Python static typing with
   https://docs.python.org/dev/library/typing.html#module-typing and mypy.
-  Allow parallel downloading.

.. |BSD3 License| image:: http://img.shields.io/badge/license-BSD3-brightgreen.svg
   :target: https://tldrlegal.com/license/bsd-3-clause-license-%28revised%29
.. |Build Status| image:: https://travis-ci.org/andrewmichaud/puckfetcher.svg?branch=master
   :target: https://travis-ci.org/andrewmichaud/puckfetcher
.. |Coverage Status| image:: https://coveralls.io/repos/andrewmichaud/puckfetcher/badge.svg?branch=master&service=github
   :target: https://coveralls.io/github/andrewmichaud/puckfetcher?branch=master
.. |Issue Count| image:: https://codeclimate.com/github/andrewmichaud/puckfetcher/badges/issue_count.svg
   :target: https://codeclimate.com/github/andrewmichaud/puckfetcher
