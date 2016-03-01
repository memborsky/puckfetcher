import logging
import os
import textwrap

import umsgpack
import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S
import puckfetcher.util as U

logger = logging.getLogger("root")


class Config():
    """Class holding config options."""

    def __init__(self, config_dir=U.CONFIG_DIR, cache_dir=U.CACHE_DIR, data_dir=U.DATA_DIR):
        self.config_dir = os.path.join(config_dir, __package__)
        logger.info("Using config dir '{0}'.".format(self.config_dir))
        self.config_file = os.path.join(self.config_dir, "config.yaml")

        self.cache_dir = os.path.join(cache_dir, __package__)
        logger.info("Using cache dir '{0}'.".format(self.cache_dir))
        self.cache_file = os.path.join(self.cache_dir, "puckcache")

        self.data_dir = os.path.join(data_dir, __package__)
        logger.info("Using data dir '{0}'.".format(self.data_dir))

        self.cached_subscriptions = []
        self.subscriptions = []

        # These are used to match user subs to cache subs, in case names or URLs (but not both)
        # have changed.
        self.cached_by_name = {}
        self.cached_by_url = {}

        self._set_file_vars()

    # "Public" functions.
    def load_state(self):
        """Load config file and subscription cache."""
        self._load_user_settings()
        self._load_cache_settings()

        if self.subscriptions != []:
            # Iterate through subscriptions to merge user settings and cache.
            subs = []
            for i, sub in enumerate(self.subscriptions):

                # Pull out settings we need for merging metadata, or to preserve over the cache.
                name = sub.name
                url = sub._provided_url
                directory = sub.directory

                # Match cached sub to current sub and take its settings.
                # If the user has changed either we can still match the sub and update settings
                # correctly.
                # If they update neither, there's nothing we can do.
                if name in self.cached_by_name:
                    logger.debug("Found {0} in cached subscriptions, merging.".format(name))
                    sub = self.cached_by_name[name]

                elif url in self.cached_by_url:
                    logger.debug(textwrap.dedent(
                        "Found sub with url {0} in cached subscriptions, merging.".format(url)))
                    sub = self.cached_by_url[url]

                sub.name = name
                sub.update_directory(directory, self.directory)
                sub.update_url(url)

                subs.append(sub)

            self.subscriptions = subs

    def save_cache(self):
        """Write current in-memory config to cache file."""
        logger.info("Writing settings to cache file '{0}'.".format(self.cache_file))
        with open(self.cache_file, "wb") as stream:
            dicts = [S.encode_subscription(sub) for sub in self.subscriptions]
            packed = umsgpack.packb(dicts)
            stream.write(packed)

    # "Private" functions (messy internals).
    def _load_cache_settings(self):
        """Load settings from cache to self.cached_settings."""
        self._ensure_file(self.cache_file)
        self.cached_subscriptions = []

        with open(self.cache_file, "rb") as stream:
            logger.info("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

        if data == b"":
            return

        for encoded_sub in umsgpack.unpackb(data):
            decoded_sub = S.decode_subscription(encoded_sub)
            self.cached_subscriptions.append(decoded_sub)

            self.cached_by_name[decoded_sub.name] = decoded_sub
            self.cached_by_url[decoded_sub._provided_url] = decoded_sub

    def _load_user_settings(self):
        """Load user settings from config file."""
        self._ensure_file(self.config_file)
        self.subscriptions = []

        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(yaml_settings, width=1, indent=4)
        logger.debug("Settings retrieved from user config file: {0}".format(pretty_settings))

        if yaml_settings is not None:
            self.directory = yaml_settings.get("directory", self.data_dir)

            for yaml_sub in yaml_settings.get("subscriptions", []):
                default_dir = os.path.expanduser(os.path.join(self.directory, yaml_sub["name"]))
                directory = yaml_sub.get("directory", default_dir)

                sub = S.parse_from_user_yaml(yaml_sub)
                sub.directory = directory

                self.subscriptions.append(sub)

    def _set_file_vars(self):
        """Set self.config_file and self.cache_file, and create directories if necessary."""
        # This code is annoyingly redundant, but I can't think of a good way to fix that.
        if not os.path.exists(self.config_dir):
            logger.debug("Config dir '{0}' does not exist, creating.".format(self.config_dir))
            os.makedirs(self.config_dir)
            self.config_file = os.path.join(self.config_dir, "config.yaml")

        elif os.path.isfile(self.config_dir):
            msg = "Config directory '{0}' is a file!".format(self.config_dir)
            E.InvalidConfigError(msg)

        if not os.path.exists(self.cache_dir):
            logger.debug("Cache dir '{0}' does not exist, creating.".format(self.cache_dir))
            os.makedirs(self.cache_dir)
            self.cache_file = os.path.join(self.cache_dir, "puckcache")

        elif os.path.isfile(self.cache_dir):
            msg = "Provided cache directory '{0}' is a file!".format(self.cache_dir)
            E.InvalidConfigError(msg)

    def _ensure_file(self, file_path):
        """Write a file at the given location with optional contents if one does not exist."""
        if os.path.exists(file_path) and not os.path.isfile(file_path):
            logger.error("Given file exists but isn't a file!")
            return

        elif not os.path.isfile(file_path):
            logger.debug("Creating empty file at '{0}'.".format(file_path))
            open(file_path, "a").close()
