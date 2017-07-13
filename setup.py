"""setuptools-based setup module for puckfetcher."""
from os import path
from setuptools import setup, find_packages

HERE = path.abspath(path.dirname(__file__))

with open(path.join(HERE, "README.rst")) as f:
    LONG_DESCRIPTION = f.read().strip()

with open(path.join(HERE, "VERSION")) as f:
    VERSION = f.read().strip()

INSTALL_REQUIRES = ["appdirs>=1.4.3, <2.0.0",
                    "clint>=0.5.1, <0.6.0",
                    "feedparser>=5.2.1, <6.0.0",
                    "pyyaml>=3.12, <4.0.0",
                    "requests>=2.14.2, <3.0.0",
                    "u-msgpack-python>=2.4.1, <3.0.0",
                    ]

TEST_REQUIRES = ["coveralls>=1.1",
                 "pytest>=3.1.0, <4.0.0",
                 ]

setup(author="Andrew Michaud",
      author_email="puckfetcher@mail.andrewmichaud.com",

      classifiers=["Development Status :: 5 - Production/Stable",
                   "Environment :: Console",
                   "Intended Audience :: End Users/Desktop",
                   "License :: OSI Approved :: BSD License",
                   "Natural Language :: English",
                   "Operating System :: MacOS :: MacOS X",
                   "Operating System :: POSIX :: Linux",
                   "Programming Language :: Python :: 3.6",
                   "Programming Language :: Python :: Implementation :: CPython",
                   "Topic :: Multimedia :: Sound/Audio",
                   "Topic :: Internet :: WWW/HTTP",
                   "Topic :: Utilities",
                   ],

      description="A simple command-line podcatcher.",

      download_url="https://github.com/andrewmichaud/puckfetcher/archive/" +
      "v{}.tar.gz".format(VERSION),

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
      tests_require=TEST_REQUIRES,

      # Project"s main homepage
      url="https://github.com/andrewmichaud/puckfetcher",

      version=VERSION)
