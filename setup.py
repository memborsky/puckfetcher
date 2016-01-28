"""
setuptools-based setup module for puckfetcher
"""

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
with open(path.join(here, "README"), encoding="utf-8") as f:
    long_description = f.read()

setup(name="puckfetcher",
      version="0.2.1",

      description="A simple podcatcher",
      long_description=long_description,

      packages=find_packages(),
      test_suite="nose.collector",
      tests_require=["nose"],

      # Project"s main homepage
      url="https://github.com/andrewmichaud/puckfetcher",

      # Author details
      author="Andrew Michaud",
      author_email="",

      license="BSD3",

      classifiers=[
          "Development Status :: 3 - Alpha"
      ],

      install_requires=["feedparser"])
