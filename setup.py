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
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(author="Andrew Michaud",
      author_email="",

      classifiers=["Development Status :: 4 - Beta"
                   "Environment :: Console",
                   "Intended Audience :: End Users/Desktop",
                   "License :: OSI Approved :: BSD License",
                   "Operating System :: MacOS :: MacOS X",
                   "Operating System :: POSIX",
                   "Programming Language :: Python",
                   "Topic :: Utilities"],

      description="A simple command-line podcatcher.",

      entry_points={
          "console_scripts": ["puckfetcher = puckfetcher.__main__:main"]
      },

      install_requires=["feedparser", "pyyaml"],

      license="BSD3",

      long_description=long_description,

      name="puckfetcher",

      packages=find_packages(),

      test_suite="nose.collector",
      tests_require=["feedparser", "nose", "requests", "pyyaml"],

      # Project"s main homepage
      url="https://github.com/andrewmichaud/puckfetcher",

      version="0.4.3")
