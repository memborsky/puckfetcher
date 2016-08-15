"""Module describing a Config object, which controls how an instance of puckfetcher acts."""

import collections
import logging
import os
from enum import Enum

import umsgpack
import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S

LOG = logging.getLogger("root")


class Config(object):
    """Class holding config options."""

    def __init__(self, config_dir, cache_dir, data_dir):

        _validate_dirs(config_dir, cache_dir, data_dir)

        self.config_file = os.path.join(config_dir, "config.yaml")
        LOG.info("Using config file '%s'.", self.config_file)

        self.cache_file = os.path.join(cache_dir, "puckcache")
        LOG.info("Using cache file '%s'.", self.cache_file)

        self.settings = {
            "directory": data_dir,
            "download_backlog": True,
            "backlog_limit": 1,
            "use_title_as_filename": False
        }

        self.state_loaded = False
        self.cached_subscriptions = []
        self.subscriptions = []

        # This map is used to match user subs to cache subs, in case names or URLs (but not both)
        # have changed.
        self.cache_map = {"by_name": {}, "by_url": {}}

        command_pairs = ((Command.update_once,
                          "Update subscriptions once. Will also download sub queues."),
                         (Command.update_forever,
                          "Update subscriptions continuously. Also downloads queues."),
                         (Command.load, "Load/reload subscriptions configuration."),
                         (Command.list, "List current subscriptions and their status."),
                         (Command.details,
                          "Provide details on one subscription's entries and queue status."),
                         (Command.enqueue,
                          "Add to a sub's download queue. Items in queue will overwrite " +
                          "existing files with same name when downloaded."),
                         (Command.download_queue, "Download a subscription's full queue."))
        self.commands = collections.OrderedDict(command_pairs)

    # "Public" functions.
    def get_commands(self):
        """Provide commands that can be used on this config."""
        return self.commands

    def load_state(self):
        """Load config file, and load subscription cache if we haven't yet."""
        self._load_user_settings()
        self._load_cache_settings()

        if self.subscriptions != []:
            # Iterate through subscriptions to merge user settings and cache.
            subs = []
            for sub in self.subscriptions:

                # Pull out settings we need for merging metadata, or to preserve over the cache.
                name = sub.name
                url = sub.url
                directory = sub.directory

                # Match cached sub to current sub and take its settings.
                # If the user has changed either we can still match the sub and update settings
                # correctly.
                # If they update neither, there's nothing we can do.
                if name in self.cache_map["by_name"].keys():
                    LOG.debug("Found sub with name %s in cached subscriptions, merging.", name)
                    sub = self.cache_map["by_name"][name]

                elif url in self.cache_map["by_url"]:
                    LOG.debug("Found sub with url %s in cached subscriptions, merging.", url)
                    sub = self.cache_map["by_url"][url]

                sub.update(directory=directory, name=name, url=url, set_original=True,
                           config_dir=self.settings["directory"])

                sub.default_missing_fields(self.settings)

                subs.append(sub)

            self.subscriptions = subs

        # Validate state after load (sanity checks, basically).
        if len(self.subscriptions) < 0:
            msg = "Something awful has happened, we have negative subscriptions"
            LOG.error(msg)
            return (False, msg)

        else:
            msg = "Successful load."
            LOG.info(msg)
            self.state_loaded = True
            return (True, msg)

    def get_subs(self):
        """Provie list of subscription names. Load state if we haven't."""
        if _ensure_loaded(self):
            subs = []
            for sub in self.subscriptions:
                subs.append(sub.name)

            return subs

        else:
            msg = "Could not load, can't provide subs."
            LOG.error(msg)
            return (False, msg)

    def update_once(self):
        """Update all subscriptions once. Return True if we successfully updated."""
        if _ensure_loaded(self):
            num_subs = len(self.subscriptions)
            for i, sub in enumerate(self.subscriptions):
                msg = "Working on sub number {}/{} - '{}'".format(i+1, num_subs, sub.name)
                LOG.info(msg)
                print(msg)
                update_successful = sub.attempt_update()

                if not update_successful:
                    msg = "Unsuccessful update for {}!".format(sub.name)
                    LOG.info(msg)
                    print(msg)

                self.subscriptions[i] = sub
                self.save_cache()

            return (True, "Update completed.")

        else:
            return (False, "Load unsuccessful, cannot update!")

    def update_forever(self):
        """Update all subscriptions continuously until terminated."""
        while True:
            try:
                (res, msg) = self.update_once()
                if not res:
                    return (res, msg)

            except KeyboardInterrupt:
                LOG.info("Stopping looping forever.")
                break

        msg = "Continuous update stopped, no issues."
        LOG.info(msg)
        return (True, msg)

    def list(self):
        """Load state and list subscriptions. Return if loading succeeded."""
        if _ensure_loaded(self):
            num_subs = len(self.subscriptions)
            print("{} subscriptions loaded.".format(num_subs))
            for i, sub in enumerate(self.subscriptions):
                print(sub.get_status(i, num_subs))

            msg = "Load + list completed, no issues."
            LOG.info(msg)
            return (True, msg)

        else:
            msg = "Load unsuccessful, cannot list subs."
            LOG.debug(msg)
            return (False, msg)

    def details(self, sub_index):
        """Get details on one sub, including last update date and what entries we have."""
        if _ensure_loaded(self):
            num_subs = len(self.subscriptions)
            sub = self.subscriptions[sub_index]
            print(sub.get_details(sub_index, num_subs))

            msg = "Load + detail completed, no issues."
            LOG.info(msg)
            return (True, msg)

        else:
            msg = "Load unsuccessful, cannot provide details."
            LOG.debug(msg)
            return (False, msg)

    def enqueue(self, sub_index, nums):
        """Add item(s) to a sub's download queue."""
        if _ensure_loaded(self):
            sub = self.subscriptions[sub_index]
            actual_nums = sub.enqueue(nums)

            msg = "Added items {} to queue successfully.".format(actual_nums)
            LOG.info(msg)
            self.save_cache()
            return (True, msg)

        else:
            msg = "Load unsuccessful, cannot enqueue items."
            LOG.debug(msg)
            return (False, msg)

    def download_queue(self, sub_index):
        """Download one sub's download queue."""
        if _ensure_loaded(self):
            num_subs = len(self.subscriptions)
            sub = self.subscriptions[sub_index]
            sub.download_queue()

            msg = "Queue downloading complete, no issues."
            LOG.info(msg)
            self.save_cache()
            return (True, msg)

        else:
            msg = "Load unsuccessful, cannot download queue."
            LOG.debug(msg)
            return (False, msg)

    def save_cache(self):
        """Write current in-memory config to cache file."""
        LOG.info("Writing settings to cache file '%s'.", self.cache_file)
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
            LOG.info("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

        if data == b"":
            return

        for encoded_sub in umsgpack.unpackb(data):
            decoded_sub = S.Subscription.decode_subscription(encoded_sub)

            if decoded_sub is not None:
                self.cached_subscriptions.append(decoded_sub)

                self.cache_map["by_name"][decoded_sub.name] = decoded_sub
                self.cache_map["by_url"][decoded_sub.original_url] = decoded_sub

    def _load_user_settings(self):
        """Load user settings from config file."""
        _ensure_file(self.config_file)
        self.subscriptions = []

        with open(self.config_file, "r") as stream:
            LOG.info("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(yaml_settings, width=1, indent=4)
        LOG.debug("Settings retrieved from user config file: %s", pretty_settings)

        if yaml_settings is not None:

            # Update self.settings, but only currently valid settings.
            for k, v in yaml_settings.items():
                if k == "subscriptions":
                    pass
                elif k not in self.settings:
                    LOG.warn("Setting %s is not a valid setting, ignoring.", k)
                else:
                    self.settings[k] = v

            for yaml_sub in yaml_settings.get("subscriptions", []):
                sub = S.Subscription.parse_from_user_yaml(yaml_sub, self.settings)
                self.subscriptions.append(sub)

def _ensure_loaded(self):
    if not self.state_loaded:
        msg = "Subscription state not loaded from cache - loading!"
        print(msg)
        LOG.info(msg)
        (res, _) = self.load_state()
        return res

    else:
        return True


def _ensure_file(file_path):
    if os.path.exists(file_path) and not os.path.isfile(file_path):
        msg = "Given file exists but isn't a file!"
        LOG.error(msg)
        raise E.InvalidConfigError(msg)

    elif not os.path.isfile(file_path):
        LOG.debug("Creating empty file at '%s'.", file_path)
        open(file_path, "a").close()


def _validate_dirs(config_dir, cache_dir, data_dir):
    for directory in [config_dir, cache_dir, data_dir]:
        if os.path.isfile(directory):
            msg = "Provided directory '{}' is a file!".format(directory)
            LOG.error(msg)
            raise E.InvalidConfigError(msg)

        if not os.path.isdir(directory):
            LOG.info("Creating nonexistent '%s'.", directory)
            os.makedirs(directory)


class Command(Enum):
    update_once = 100
    update_forever = 101
    load = 102
    list = 103
    details = 104
    enqueue = 105
    download_queue = 106
