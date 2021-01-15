"""setuptools-based setup module for puckfetcher."""
from os import path
from setuptools import setup, find_packages

HERE = path.abspath(path.dirname(__file__))

with open(path.join(HERE, "README.rst")) as f:
    LONG_DESCRIPTION = f.read().strip()

with open(path.join(HERE, "VERSION")) as f:
    VERSION = f.read().strip()

URL = "https://github.com/alixnovosi/puckfetcher"

INSTALL_REQUIRES = [
    "appdirs>=1.4.4, <2.0.0",
    "clint>=0.5.1, <0.6.0",
    "feedparser>=6.0.2, <7.0.0",
    "pyyaml>=5.3.1, <6.0.0",
    "python-magic>=0.4.18, <0.5.0",
    "requests>=2.25.1, <3.0.0",
    "u-msgpack-python>=2.7.1, <3.0.0",
    "stagger>=1.0.0, <2.0.0",
    "drewtilities>=1.3.2, <2.0.0",
]

TEST_REQUIRES = [
    "coveralls>=3.0.0, <4.0.0",
    "pytest>=6.2.1, <7.0.0",
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
                   "Programming Language :: Python :: 3.7",
                   "Programming Language :: Python :: 3.8",
                   "Programming Language :: Python :: 3.9",
                   "Programming Language :: Python :: Implementation :: CPython",
                   "Topic :: Multimedia :: Sound/Audio",
                   "Topic :: Internet :: WWW/HTTP",
                   "Topic :: Utilities",
                   "Typing :: Typed",
                  ],

      name="puckfetcher",
      description="A simple command-line podcatcher.",
      download_url=f"{URL}/archive/v{VERSION}.tar.gz",
      url=f"{URL}",
      keywords=["music", "podcasts", "rss"],
      license="BSD3",

      entry_points={
          "console_scripts": ["puckfetcher = puckfetcher.__main__:main"]
      },

      package_data={
          ".": ["VERSION", "example_config.yaml"],
      },

      setup_requires=["pytest-runner"],
      python_requires=">=3.6",

      packages=find_packages(),
      long_description=LONG_DESCRIPTION,
      install_requires=INSTALL_REQUIRES,
      tests_require=TEST_REQUIRES,
      version=VERSION,
      )
