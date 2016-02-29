"""setuptools-based setup module for puckfetcher."""

# Modeled on Python sample project setup.py -
# https://github.com/pypa/sampleproject
# Prefer setuptools over distutils.
from setuptools import setup, find_packages

# Use a consistent encoding.
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file.
# Python standard seems to be .rst, but I prefer Markdown.
with open(path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

# Retrieve version.
with open(path.join(here, "VERSION"), encoding="utf-8") as f:
    version = f.read()

setup(author="Andrew Michaud",
      author_email="",

      classifiers=["Development Status :: 4 - Beta"
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

      entry_points={
          "console_scripts": ["puckfetcher = puckfetcher.__main__:main"]
      },

      install_requires=["clint", "feedparser", "pyyaml", "requests", "u-msgpack-python"],

      license="BSD3",

      long_description=long_description,

      name="puckfetcher",

      packages=find_packages(),

      setup_requires=["pytest-runner"],

      test_suite="tests",
      tests_require=["coveralls", "pytest"],

      # Project"s main homepage
      url="https://github.com/andrewmichaud/puckfetcher",

      version=version)
