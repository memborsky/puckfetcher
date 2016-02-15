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

        self.settings = None
        self.config_dir = config_dir
        self.config_file = None
        self.cache_dir = cache_dir
        self.cache_file = None
        self.data_dir = data_dir

        self.subscription_cache = None
        self.subscriptions = []
        self.subscription_map = {}

        self.load_state()

    def load_state(self):
        """Load config file and subscription cache."""

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

        # Ensure the cache dir the user specified exists and is a directory.
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
                E.InvalidcacheError(msg)
            else:
                logger.info("Using provided cache dir '{0}'.".format(self.cache_dir))

        self.cache_file = os.path.join(self.cache_dir, "puckcache")

        # Write default configuration file if one does not exist.
        if not os.path.exists(self.config_file):
            logger.debug(textwrap.dedent(
                """\
                Config file {0} does not exist, creating with default settings.\
                """.format(self.config_file)))

            with open(self.config_file, "w", ) as stream:
                # TODO write default options
                # TODO write example podcast
                stream.write("# Created by puckfetcher")

        # Retrieve settings from config file.
        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            self.settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(self.settings, width=1, indent=4)

        logger.debug("Settings retrieved from user config file: {0}".format(pretty_settings))

        # Retrieve settings from cache.
        # NOTE Currently we only use subscriptions, but we might want to cache other settings
        # later.
        cached_subs = None
        if self.cache_file is not None and os.path.isfile(self.cache_file):
            with open(self.cache_file, "rb") as stream:
                logger.info("Opening subscription cache to retrieve subscriptions.")
                data = stream.read()
                # TODO I feel like msgpack must be able to handle this, but maybe not.
                if data is not None and len(data) > 0:
                    cached_subs = msgpack.unpackb(data, object_hook=S.decode_subscription)

        # Use only user-defined subs. If a subscription is removed from the config file, it's gone.
        subs = []
        if cached_subs is not None:

            if self.settings is None:
                self.subscriptions = cached_subs
                self.settings = {}
                self.settings["subscriptions"] = cached_subs
                return

            else:
                cached_by_name = {sub.name: sub for sub in cached_subs}
                cached_by_url = {sub._provided_url: sub for sub in cached_subs}

                for i, sub in enumerate(self.settings["subscriptions"]):
                    name = sub["name"]
                    url = sub["url"]

                    if name in cached_by_name:
                        sub = cached_by_name[name]
                        sub._provided_url = url
                        sub._current_url = url
                    elif url in cached_by_url:
                        sub = cached_by_url[url]
                        sub._provided_url = url
                        sub._current_url = url

                    subs.append(sub)

        self.subscriptions = [S.parse_from_user_yaml(s) for s in subs]

    def save_cache(self):
        """Write current in-memory config to cache file."""
        # Write current settings.
        logger.info("Writing settings to cache file '{0}'.".format(self.cache_file))
        with open(self.cache_file, "wb") as stream:
            packed = msgpack.packb(self.subscriptions, default=S.encode_subscription)
            stream.write(packed)
