import copy
import logging
import os
import textwrap

import msgpack
import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S
import puckfetcher.util as U

logger = logging.getLogger("root")


class Config():
    """Class holding config options."""

    def __init__(self, config_dir=None, cache_dir=None, data_dir=None):
        self.config_dir = config_dir
        self.config_file = None

        self.cache_dir = cache_dir
        self.cache_file = None

        self.data_dir = data_dir

        self.subscriptions = []

        self.cached_by_name = {}
        self.cached_by_url = {}
        self.settings = {}
        self.cached_settings = {}

        self._get_config_file()
        self._get_cache_file()

        self.load_state()

    def _get_config_file(self):
        """Set self.config_file."""
        # Ensure the config dir the user specified exists and is a directory.
        if self.config_dir is None:
            # This will also create the directory.
            self.config_dir = U.get_xdg_config_dir_path("puckfetcher")
            logger.info("No config dir provided, using default '{0}'.".format(self.config_dir))

        else:
            if not os.path.exists(self.config_dir):
                logger.debug("Config dir '{0}' does not exist, creating.".format(self.config_dir))
                os.makedirs(self.config_dir)

            elif os.path.exists(self.config_dir) and os.path.isfile(self.config_dir):
                msg = "Config directory '{0}' is a file!".format(self.config_dir)
                E.InvalidConfigError(msg)

            else:
                logger.info("Using provided config dir '{0}'.".format(self.config_dir))

        self.config_file = os.path.join(self.config_dir, "config.yaml")

    def _get_cache_file(self):
        """Set self.cache_file."""
        if self.cache_dir is None:
            # This will also create the directory.
            self.cache_dir = U.get_xdg_cache_dir_path("puckfetcher")
            logger.info("No cache dir provided, using default '{0}'.".format(self.cache_dir))

        else:
            if not os.path.exists(self.cache_dir):
                logger.debug("Cache dir '{0}' does not exist, creating.".format(self.cache_dir))
                os.makedirs(self.cache_dir)

            elif os.path.exists(self.cache_dir) and os.path.isfile(self.cache_dir):
                msg = "Provided cache directory '{0}' is a file!".format(self.cache_dir)
                E.InvalidCacheError(msg)

            else:
                logger.info("Using provided cache dir '{0}'.".format(self.cache_dir))

        self.cache_file = os.path.join(self.cache_dir, "puckcache")

    def _ensure_config(self):
        """If there is no config file, write one with default settings."""
        if not os.path.exists(self.config_file):
            logger.debug("Creating file {0} with default settings.".format(self.config_file))

            open(self.config_file, "a").close()
            with open(self.config_file, "w") as stream:
                example_config = os.path.join(os.path.dirname(__file__), "example_config.yaml")

                with open(example_config, "r") as example:
                    text = example.read()
                    stream.write(text)

    def _load_user_settings(self):
        """Load user settings from config file to self.settings."""
        self._ensure_config()
        yaml_settings = ""

        # Retrieve settings from config file.
        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        if self.data_dir is not None and yaml_settings is not None:
            yaml_settings["directory"] = self.data_dir

        pretty_settings = yaml.dump(self.settings, width=1, indent=4)
        logger.debug("Settings retrieved from user config file: {0}".format(pretty_settings))

        if yaml_settings is not None:
            self.settings["directory"] = yaml_settings.get("directory", None)

            if yaml_settings.get("subscriptions", None) is not None:
                self.settings["subscriptions"] = [S.parse_from_user_yaml(sub) for sub in
                                                  yaml_settings["subscriptions"]]

    def _ensure_cache_file(self):
        """If there is no cache file, write an empty one."""
        if not os.path.isfile(self.cache_file):
            logger.debug("Creating empty cache file at '{0}'.".format(self.cache_file))
            open(self.cache_file, "a").close()

    def _load_cache_settings(self):
        """Load settings from cache to self.cached_settings."""
        self._ensure_cache_file()

        with open(self.cache_file, "rb") as stream:
            logger.info("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

            if data is not None and len(data) > 0:
                # self.cached_settings = msgpack.unpackb(data)
                self.cached_settings["subscriptions"] = msgpack.unpackb(data,
                                                                object_hook=S.decode_subscription)

                subs = self.cached_settings["subscriptions"]

                # These are used to match user subs to cache subs, in case names or URLs (but not
                # both) have changed.
                self.cached_by_name = {sub.name: sub for sub in subs}
                self.cached_by_url = {sub._provided_url for sub in subs}

    def load_state(self):
        """Load config file and subscription cache."""
        self._load_user_settings()
        self._load_cache_settings()

        print(self.settings)

        # Nothing to do.
        if self.cached_settings == {}:
            return

        elif self.settings == {}:
            self.settings = copy.deepcopy(self.cached_settings)
            return

        else:
            # Iterate through subscriptions to merge user settings and cache.
            for i, sub in enumerate(self.settings["subscriptions"]):

                # Pull out settings we need for merging metadata, or to preserve over the cache.
                name = sub.name
                url = sub._provided_url
                directory = sub.directory

                # Match cached sub to current sub and take its settings.
                if name in self.cached_by_name:
                    sub = self.cached_by_name[name]

                elif url in self.cached_by_url:
                    sub = self.cached_by_url[url]

                # Update provided URL if user has changed it.
                if url != sub._provided_url:
                    sub._provided_url = copy.deepcopy(url)
                    sub._current_url = copy.deepcopy(url)

                # Update directory, detecting if it is an absolute path and taking config directory
                # into consideration.
                # Watch for user updating config directory on us.
                if sub.directory != directory:
                    if directory is None or directory == "":
                        E.InvalidConfigError(desc=textwrap.dedent(
                            """\
                            Provided invalid sub directory '{0}' for '{1}'.\
                            """.format(directory, name)))

                    else:

                        # NOTE This may not be fully portable. Should work at least on OSX and Linux.
                        if directory[0] == os.path.sep:
                            sub.directory = directory

                        else:
                            sub.directory = os.path.join(self.data_dir, directory)

                self.settings["subscriptions"].append(sub)

    def save_cache(self):
        """Write current in-memory config to cache file."""
        logger.info("Writing settings to cache file '{0}'.".format(self.cache_file))
        with open(self.cache_file, "wb") as stream:
            packed = msgpack.packb(self.settings["subscriptions"], default=S.encode_subscription)
            stream.write(packed)
