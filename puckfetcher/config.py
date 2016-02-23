import copy
import logging
import os

import msgpack
import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S
import puckfetcher.util as U

logger = logging.getLogger("root")


class Config():
    """Class holding config options."""

    def __init__(self, config_dir=U.CONFIG_DIR, cache_dir=U.CACHE_DIR, data_dir=U.DATA_DIR):
        self.config_dir = config_dir
        logger.info("Using config dir '{0}'.".format(self.config_dir))
        self.config_file = os.path.join(self.config_dir, "config.yaml")

        self.cache_dir = cache_dir
        logger.info("Using cache dir '{0}'.".format(self.cache_dir))
        self.cache_file = os.path.join(self.cache_dir, "puckcache")

        self.data_dir = data_dir
        logger.info("Using data dir '{0}'.".format(self.data_dir))

        self._get_config_file()
        self._get_cache_file()

        self.load_state()

    def _get_config_file(self):
        """Set self.config_file."""
        if not os.path.exists(self.config_dir):
            logger.debug("Config dir '{0}' does not exist, creating.".format(self.config_dir))
            os.makedirs(self.config_dir)
            self.config_file = os.path.join(self.config_dir, "config.yaml")

        elif os.path.exists(self.config_dir) and os.path.isfile(self.config_dir):
            msg = "Config directory '{0}' is a file!".format(self.config_dir)
            E.InvalidConfigError(msg)

    def _get_cache_file(self):
        """Set self.cache_file."""
        if not os.path.exists(self.cache_dir):
            logger.debug("Cache dir '{0}' does not exist, creating.".format(self.cache_dir))
            os.makedirs(self.cache_dir)
            self.cache_file = os.path.join(self.cache_dir, "puckcache")

        elif os.path.exists(self.cache_dir) and os.path.isfile(self.cache_dir):
            msg = "Provided cache directory '{0}' is a file!".format(self.cache_dir)
            E.InvalidConfigError(msg)

    def _ensure_file(self, file_path, contents=""):
        """Write a file at the given location with optional contents if one does not exist."""
        if os.path.exists(file_path) and not os.path.isfile(file_path):
            logger.error("Given file exists but isn't a file!")
            return

        elif not os.path.isfile(file_path):
            logger.debug("Creating empty file at '{0}' with contents {1}.".format(file_path,
                                                                                  contents))
            with open(file_path, "a") as f:
                f.write(contents)

    def _load_user_settings(self):
        """Load user settings from config file to self.settings."""
        example_config = os.path.join(os.path.dirname(__file__), "example_config.yaml")
        with open(example_config, "r") as example:
            contents = example.read()

        self._ensure_file(self.config_file, contents)

        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(self.settings, width=1, indent=4)
        logger.debug("Settings retrieved from user config file: {0}".format(pretty_settings))

        if yaml_settings is not None:
            self.directory = yaml_settings.get("directory", self.data_dir)

            if yaml_settings.get("subscriptions", None) is not None:
                self.subscriptions = [S.parse_from_user_yaml(sub) for sub in
                                                  yaml_settings["subscriptions"]]

    def _load_cache_settings(self):
        """Load settings from cache to self.cached_settings."""
        self._ensure_file(self.cache_file)

        with open(self.cache_file, "rb") as stream:
            logger.info("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

        if data is None or len(data) <= 0:
            return

        self.cached_subscriptions = msgpack.unpackb(data, object_hook=S.decode_subscription)

        subs = self.subscriptions

        # These are used to match user subs to cache subs, in case names or URLs (but not
        # both) have changed.
        self.cached_by_name = {sub.name: sub for sub in subs}
        self.cached_by_url = {sub._provided_url for sub in subs}

    def load_state(self):
        """Load config file and subscription cache."""
        self._load_user_settings()
        self._load_cache_settings()

        # Nothing to do.
        if self.cached_subscriptions == {}:
            return

        elif self.settings == {}:
            self.subscriptions = copy.deepcopy(self.cached_subscriptions)
            return

        else:
            # Iterate through subscriptions to merge user settings and cache.
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
                    sub = self.cached_by_name[name]

                elif url in self.cached_by_url:
                    sub = self.cached_by_url[url]

                sub.update_directory(directory, self.data_dir)
                sub.update_url(url)

                self.subscriptions.append(sub)

    def save_cache(self):
        """Write current in-memory config to cache file."""
        logger.info("Writing settings to cache file '{0}'.".format(self.cache_file))
        with open(self.cache_file, "wb") as stream:
            packed = msgpack.packb(self.subscriptions, default=S.encode_subscription)
            stream.write(packed)
