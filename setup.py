"""setuptools-based setup module for puckfetcher."""

# Modeled on Python sample project setup.py - https://github.com/pypa/sampleproject
# Use a consistent encoding.
import codecs
import sys
from os import path
# Prefer setuptools over distutils.
from setuptools import setup, find_packages

HERE = path.abspath(path.dirname(__file__))

# Get the long description from the README file.
# Python standard seems to be .rst, but I prefer Markdown.
with codecs.open(path.join(HERE, "README.rst"), encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

# Retrieve version.
with codecs.open(path.join(HERE, "VERSION"), encoding="utf-8") as f:
    VERSION = f.read()

# Use enum34 to allow enums in Python 3.3 and 2.7.
INSTALL_REQUIRES = ["appdirs", "clint", "feedparser", "pyyaml", "requests", "u-msgpack-python"]
if sys.version_info < (3, 4):
    INSTALL_REQUIRES += ["enum34"]

setup(author="Andrew Michaud",
      author_email="andrewjmichaud+puckfetcher@gmail.com",

      classifiers=["Development Status :: 4 - Beta",
                   "Environment :: Console",
                   "Intended Audience :: End Users/Desktop",
                   "License :: OSI Approved :: BSD License",
                   "Natural Language :: English",
                   "Operating System :: MacOS :: MacOS X",
                   "Operating System :: POSIX :: Linux",
                   "Programming Language :: Python :: 2.7",
                   "Programming Language :: Python :: 3.3",
                   "Programming Language :: Python :: 3.4",
                   "Programming Language :: Python :: 3.5",
                   "Topic :: Multimedia :: Sound/Audio",
                   "Topic :: Internet :: WWW/HTTP",
                   "Topic :: Utilities"],

      description="A simple command-line podcatcher.",

      download_url="https://github.com/andrewmichaud/puckfetcher/tarball/" + VERSION,

      entry_points={
          "console_scripts": ["puckfetcher = puckfetcher.__main__:main"]
      },

      install_requires=INSTALL_REQUIRES,

      keywords=["music", "podcasts", "rss"],

      license="BSD3",

      long_description=LONG_DESCRIPTION,

      name="puckfetcher",

      packages=find_packages(),

      setup_requires=["pytest-runner"],

      test_suite="tests",
      tests_require=["coveralls", "pytest"],

      # Project"s main homepage
      url="https://github.com/andrewmichaud/puckfetcher",

      version=VERSION)
