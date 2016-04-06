"""Module describing a Config object, which controls how an instance of puckfetcher acts."""
import logging
import os

import umsgpack
import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S

logger = logging.getLogger("root")


class Config(object):
    """Class holding config options."""

    def __init__(self, config_dir, cache_dir, data_dir):

        _validate_dirs(config_dir, cache_dir, data_dir)

        self.config_file = os.path.join(config_dir, "config.yaml")
        logger.info("Using config file '%s'.", self.config_file)

        self.cache_file = os.path.join(cache_dir, "puckcache")
        logger.info("Using cache dir '%s'.", self.cache_file)

        self.data_dir = data_dir
        self.directory = None

        self.cached_subscriptions = []
        self.subscriptions = []

        # This map is used to match user subs to cache subs, in case names or URLs (but not both)
        # have changed.
        self.cache_map = {"by_name": {}, "by_url": {}}

    # "Public" functions.
    def load_state(self):
        """Load config file and subscription cache."""
        self._load_user_settings()
        self._load_cache_settings()

        if self.subscriptions != []:
            # Iterate through subscriptions to merge user settings and cache.
            subs = []
            for sub in self.subscriptions:

                # Pull out settings we need for merging metadata, or to preserve over the cache.
                name = sub.name
                url = sub._provided_url
                directory = sub.directory

                # Match cached sub to current sub and take its settings.
                # If the user has changed either we can still match the sub and update settings
                # correctly.
                # If they update neither, there's nothing we can do.
                if name in self.cache_map["by_name"].keys():
                    logger.debug("Found sum with name %s in cached subscriptions, merging.", name)
                    sub = self.cache_map["by_name"][name]

                elif url in self.cache_map["by_url"]:
                    logger.debug("Found sub with url %s in cached subscriptions, merging.", url)
                    sub = self.cache_map["by_url"][url]

                sub.name = name
                sub.update_directory(directory, self.directory)
                sub.update_url(url)

                subs.append(sub)

            self.subscriptions = subs

        # Validate state after load (sanity checks, basically).
        if len(self.subscriptions) < 0:
            logger.error("Something awful has happened, we have negative subscriptions")
            return False

        else:
            return True

    def update_once(self):
        """Update all subscriptions once. Return True if we successfully updated."""
        load_successful = self.load_state()
        if load_successful:
            num_subs = len(self.subscriptions)
            for i, sub in enumerate(self.subscriptions):
                print("Working on sub number {}/{} - '{}'".format(i+1, num_subs, sub.name))
                update_successful = sub.attempt_update()
                if update_successful:
                    print("Successful update.")
                else:
                    print("Unsuccessful update!")
                    continue

                self.subscriptions[i] = sub
                self.save_cache()

            return True

        else:
            logger.debug("Load unsuccessful, cannot update.")
            return False

    def update_forever(self):
        """Update all subscriptions continuously until terminated."""
        while True:
            try:
                self.update_once()

            except KeyboardInterrupt:
                logger.info("Stopping looping forever.")
                break

    def list(self):
        """Load state and list subscriptions. Return if loading succeeded."""
        load_successful = self.load_state()
        if load_successful:
            num_subs = len(self.subscriptions)
            print("{} subscriptions loaded.".format(num_subs))
            for i, sub in enumerate(self.subscriptions):
                print("Sub number {}/{} - '{}'".format(i+1, num_subs, sub.name))

            return True

        else:
            logger.debug("Load unsuccessful, cannot update.")
            return False

    def save_cache(self):
        """Write current in-memory config to cache file."""
        logger.info("Writing settings to cache file '%s'.", self.cache_file)
        with open(self.cache_file, "wb") as stream:
            dicts = [S.Subscription.encode_subscription(sub) for sub in self.subscriptions]
            packed = umsgpack.packb(dicts)
            stream.write(packed)

    # "Private" functions (messy internals).
    def _load_cache_settings(self):
        """Load settings from cache to self.cached_settings."""
        _ensure_file(self.cache_file)
        self.cached_subscriptions = []

        with open(self.cache_file, "rb") as stream:
            logger.info("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

        if data == b"":
            return

        for encoded_sub in umsgpack.unpackb(data):
            decoded_sub = S.Subscription.decode_subscription(encoded_sub)
            self.cached_subscriptions.append(decoded_sub)

            self.cache_map["by_name"][decoded_sub.name] = decoded_sub
            self.cache_map["by_url"][decoded_sub._provided_url] = decoded_sub

    def _load_user_settings(self):
        """Load user settings from config file."""
        _ensure_file(self.config_file)
        self.subscriptions = []

        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(yaml_settings, width=1, indent=4)
        logger.debug("Settings retrieved from user config file: %s", pretty_settings)

        if yaml_settings is not None:
            self.directory = yaml_settings.get("directory", self.data_dir)

            for yaml_sub in yaml_settings.get("subscriptions", []):
                default_dir = os.path.expanduser(os.path.join(self.directory, yaml_sub["name"]))
                directory = yaml_sub.get("directory", default_dir)

                sub = S.Subscription.parse_from_user_yaml(yaml_sub)
                sub.directory = directory

                self.subscriptions.append(sub)


def _ensure_file(file_path):
    if os.path.exists(file_path) and not os.path.isfile(file_path):
        msg = "Given file exists but isn't a file!"
        logger.error(msg)
        raise E.InvalidConfigError(msg)

    elif not os.path.isfile(file_path):
        logger.debug("Creating empty file at '%s'.", file_path)
        open(file_path, "a").close()


def _validate_dirs(config_dir, cache_dir, data_dir):
    for directory in [config_dir, cache_dir, data_dir]:
        if os.path.isfile(directory):
            msg = "Provided directory '{}' is a file!".format(directory)
            logger.error(msg)
            raise E.InvalidConfigError(msg)

        if not os.path.isdir(directory):
            logger.info("Creating nonexistent '%s'.", directory)
            os.makedirs(directory)
