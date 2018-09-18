"""Module describing a Config object, which controls how an instance of puckfetcher acts."""
import collections
import enum
import logging
import os
from typing import Any, List, Mapping, Dict

import drewtilities as util
import umsgpack
import yaml

import puckfetcher.constants as constants
import puckfetcher.error as error
import puckfetcher.subscription as subscription

SUMMARY_LIMIT = 4


LOG = logging.getLogger("root")


class Config(object):
    """Class holding config options."""

    def __init__(self, config_dir: str, cache_dir: str, data_dir: str) -> None:
        _validate_dirs(config_dir, cache_dir, data_dir)

        self.config_file = os.path.join(config_dir, "config.yaml")
        LOG.debug(f"Using config file '{self.config_file}'.")

        self.cache_file = os.path.join(cache_dir, "puckcache")
        LOG.debug(f"Using cache file '{self.cache_file}'.")

        self.settings = {
            "directory": data_dir,
            "backlog_limit": 1,
            "use_title_as_filename": False,
            "set_tags": False,
        }

        self.state_loaded = False
        self.subscriptions: List[subscription.Subscription] = []

        # This map is used to match user subs to cache subs, in case names or URLs (but not both)
        # have changed.
        self.cache_map: Dict[str, Dict[str, subscription.Subscription]] = {
            "by_name": {},
            "by_url": {},
        }

    # "Public" functions.
    def load_state(self) -> None:
        """Load config file, and load subscription cache if we haven't yet."""
        try:
            self._load_user_settings()
        except error.MalformedConfigError as e:
            LOG.error(f"Error loading user settings: {e}")
            raise

        try:
            self._load_cache_settings()
        except error.MalformedConfigError as e:
            LOG.error(f"Error loading cache settings: {e}")
            raise

        if self.subscriptions != []:
            # Iterate through subscriptions to merge user settings and cache.
            subs = []
            for sub in self.subscriptions:

                # Items we want to use to look up subs in maps.
                name = sub.metadata["name"]
                url = sub.url

                # Items where we want to favor user settings over cache settings.
                directory = sub.directory
                settings = sub.settings
                metadata = sub.metadata

                # Match cached sub to current sub and take its settings.
                # If the user has changed either we can still match the sub and update settings
                # correctly.
                # If they update neither, there's nothing we can do.
                if name in self.cache_map["by_name"]:
                    LOG.debug(f"Found sub with name '{name}' in cached subscriptions, merging.")
                    sub = self.cache_map["by_name"][name]

                elif url in self.cache_map["by_url"]:
                    LOG.debug(f"Found sub with url '{url}' in cached subscriptions, merging.")
                    sub = self.cache_map["by_url"][url]

                sub.update(directory=directory, name=name, url=url, set_original=True,
                           config_dir=self.settings["directory"], settings=settings,
                           metadata=metadata
                          )

                sub.default_missing_fields(self.settings)

                subs.append(sub)

            self.subscriptions = subs

        LOG.debug("Successful load.")
        self.state_loaded = True

    def get_subs(self) -> List[str]:
        """Provide list of subscription names. Load state if we haven't."""
        _ensure_loaded(self)
        subs = []
        for sub in self.subscriptions:
            subs.append(sub.metadata["name"])

        return subs

    def update(self) -> None:
        """Update all subscriptions once."""
        _ensure_loaded(self)

        num_subs = len(self.subscriptions)
        for i, sub in enumerate(self.subscriptions):
            LOG.info(f"Working on sub number {i+1}/{num_subs} - '{sub.metadata['name']}'")
            update_successful = sub.attempt_update()

            if update_successful:
                LOG.info(f"Updated sub '{sub.metadata['name']}' successfully.\n")
            else:
                LOG.info(f"Unsuccessful update for sub '{sub.metadata['name']}'.\n")

            self.subscriptions[i] = sub
            self.save_cache()

    def list(self) -> None:
        """Load state and list subscriptions."""
        _ensure_loaded(self)

        num_subs = len(self.subscriptions)
        LOG.info(f"{num_subs} subscriptions loaded.")
        for i, sub in enumerate(self.subscriptions):
            LOG.info(sub.get_status(i, num_subs))

        LOG.debug("Load + list completed, no issues.")

    def details(self, sub_index: int) -> None:
        """Get details on one sub, including last update date and what entries we have."""
        self._validate_command(sub_index)

        num_subs = len(self.subscriptions)
        sub = self.subscriptions[sub_index]
        sub.get_details(sub_index, num_subs)

        LOG.debug("Load + detail completed, no issues.")

    def enqueue(self, sub_index: int, nums: List[int]) -> None:
        """Add item(s) to a sub's download queue."""
        self._validate_list_command(sub_index, nums)

        sub = self.subscriptions[sub_index]

        # Implicitly mark subs we're manually adding to the queue as undownloaded. User shouldn't
        # have to manually do that.
        sub.unmark(nums)
        enqueued_nums = sub.enqueue(nums)

        LOG.info(f"Added items {enqueued_nums} to queue successfully.")
        self.save_cache()

    def mark(self, sub_index: int, nums: List[int]) -> None:
        """Mark items as downloaded by a subscription."""
        self._validate_list_command(sub_index, nums)

        sub = self.subscriptions[sub_index]
        marked_nums = sub.mark(nums)

        LOG.info(f"Marked items {marked_nums} as downloaded successfully.")
        self.save_cache()

    def unmark(self, sub_index: int, nums: List[int]) -> None:
        """Unmark items as downloaded by a subscription."""
        self._validate_list_command(sub_index, nums)

        sub = self.subscriptions[sub_index]
        unmarked_nums = sub.unmark(nums)

        LOG.info(f"Unmarked items {unmarked_nums} successfully.")
        self.save_cache()

    def summarize(self) -> None:
        """
        Provide summary of recently downloaded entries. Show only items downloaded in this session.
        """
        lines = []

        lines.append("Items downloaded in this session:")
        if len(self.subscriptions) == 0:
            lines.append("No items downloaded in this session.")
            lines.append("")

        # Skip subs we haven't downloaded anything for in this session.
        for sub in self.subscriptions:
            summary_list = list(sub.session_summary())[0:SUMMARY_LIMIT]
            if len(summary_list) > 0:
                lines.append(sub.metadata["name"])

                for item in summary_list:
                    lines.append(f"    {item}")

                lines.append("")

        LOG.info("\n".join(lines))

    def summarize_sub(self, sub_index: int) -> None:
        """Provide summary of recently downloaded entries for a single subscription."""
        self._validate_command(sub_index)

        sub = self.subscriptions[sub_index]

        lines = []

        lines.append(f"Items recently downloaded for {sub.metadata['name']}:")

        summary_list = sub.full_summary()
        if len(summary_list) == 0:
            lines.append("    No items downloaded.")

        for item in summary_list:
            lines.append(f"    {item}")

        lines.append("")

        LOG.info("\n".join(lines))

    def download_queue(self, sub_index: int) -> None:
        """Download one sub's download queue."""
        self._validate_command(sub_index)

        sub = self.subscriptions[sub_index]
        sub.download_queue()

        LOG.info("Queue downloading complete, no issues.")
        self.save_cache()

    def save_cache(self) -> None:
        """Write current in-memory config to cache file."""
        LOG.debug(f"Writing settings to cache file '{self.cache_file}'.")
        with open(self.cache_file, "wb") as stream:
            dicts = [subscription.Subscription.encode_subscription(s) for s in self.subscriptions]
            packed = umsgpack.packb(dicts)
            stream.write(packed)

    def reload_config(self) -> None:
        """Reload config file."""
        self.save_cache()
        self.load_state()
        LOG.info("Reloaded")

    # "Private" functions (messy internals).
    def _validate_list_command(self, sub_index: int, nums: List[int]) -> None:
        if nums is None or len(nums) <= 0:
            raise error.BadCommandError(f"Invalid list of nums {nums}.")

        self._validate_command(sub_index)

    def _validate_command(self, sub_index: int) -> None:
        if sub_index < 0 or sub_index > len(self.subscriptions):
            raise error.BadCommandError(f"Invalid sub index {sub_index}.")

        _ensure_loaded(self)

    def _load_cache_settings(self) -> None:
        """Load settings from cache to self.cached_settings."""
        _ensure_file(self.cache_file)

        with open(self.cache_file, "rb") as stream:
            LOG.debug("Opening subscription cache to retrieve subscriptions.")
            data = stream.read()

        if data == b"":
            LOG.debug("Received empty string from cache.")
            return

        for encoded_sub in umsgpack.unpackb(data):
            try:
                decoded_sub = subscription.Subscription.decode_subscription(encoded_sub)

            except error.MalformedSubscriptionError as exception:
                LOG.debug("Encountered error in subscription decoding:")
                LOG.debug(exception.desc)
                LOG.debug("Skipping this sub.")
                continue

            self.cache_map["by_name"][decoded_sub.metadata["name"]] = decoded_sub
            self.cache_map["by_url"][decoded_sub.original_url] = decoded_sub

    def _load_user_settings(self) -> None:
        """Load user settings from config file."""
        _ensure_file(self.config_file)

        self.subscriptions = []

        with open(self.config_file, "r", encoding=constants.ENCODING) as stream:
            LOG.debug("Opening config file to retrieve settings.")
            yaml_settings = yaml.safe_load(stream)

        pretty_settings = yaml.dump(yaml_settings, width=1, indent=4)
        LOG.debug(f"Settings retrieved from user config file: {pretty_settings}")

        if yaml_settings is not None:
            # Process valid settings. Ignore garbage if the user gave it to us.
            for name, value in yaml_settings.items():
                if name == "subscriptions":
                    pass
                elif name not in self.settings:
                    LOG.debug(f"Setting {name} is not a valid setting, ignoring.")
                else:
                    self.settings[name] = value

            fail_count = 0
            for i, yaml_sub in enumerate(yaml_settings.get("subscriptions", [])):
                sub = subscription.Subscription.parse_from_user_yaml(yaml_sub, self.settings)

                if sub is None:
                    LOG.debug(f"Unable to parse user YAML for sub #{i+1} - something is wrong.")
                    fail_count += 1
                    continue

                self.subscriptions.append(sub)

            if fail_count > 0:
                LOG.error("Some subscriptions from config file couldn't be parsed - check logs.")

def get_commands() -> Mapping[Any, str]:
    """Provide commands that can be used on a config."""
    return collections.OrderedDict((
        (Command.exit,
         "Exit application."),
        (Command.update,
         "Update all subscriptions. Will also download sub queues."),
        (Command.list,
         "List current subscriptions and their status."),
        (Command.details,
         "Provide details on one subscription's entries and queue status."),
        (Command.enqueue,
         "Add to a sub's download queue. Items will be skipped if already in queue, or invalid."),
        (Command.mark,
         "Mark a subscription entry as downloaded."),
        (Command.unmark,
         "Mark a subscription entry as not downloaded. Will not queue for download."),
        (Command.download_queue,
         "Download a subscription's full queue. Files with the same name as a to-be-downloaded "
         "entry will be overridden."),
        (Command.summarize,
         "Summarize subscription entries downloaded in this session."),
        (Command.summarize_sub,
         "Summarize recent entries downloaded for a specific sub."),
        (Command.reload_config,
         "Reload configuration file."),
    ))

def get_command_help() -> str:
    """Get name and summary for all available commands."""
    command_help_list = []
    for command, help_text in get_commands().items():
        command_help_list.append(f"{command.name:<14} - {help_text}")

    return "\n".join(command_help_list)


def _ensure_loaded(config: Config) -> None:
    if not config.state_loaded:
        LOG.debug("State not loaded from config file and cache - loading!")
        config.load_state()


def _ensure_file(file_path: str) -> None:
    if os.path.exists(file_path) and not os.path.isfile(file_path):
        msg = f"Given file {file_path} exists but isn't a file."
        LOG.debug(msg)
        raise error.MalformedConfigError(msg)

    elif not os.path.isfile(file_path):
        LOG.debug(f"Creating empty file at '{file_path}'.")

        try:
            open(file_path, "a", encoding=constants.ENCODING).close()

        except PermissionError as e:
            raise error.MalformedConfigError(f"No permissions to access path {file_path}.")

        except FileNotFoundError as e:
            raise error.MalformedConfigError(f"File path {file_path} is invalid.")


def _validate_dirs(config_dir: str, cache_dir: str, data_dir: str) -> None:
    for directory in [config_dir, cache_dir, data_dir]:
        if os.path.isfile(directory):
            raise error.MalformedConfigError(f"Provided directory '{directory}' "
                                             "is actually a file!")

        util.ensure_dir(directory)


class Command(enum.Enum):
    """Commands a Config can perform."""
    exit = 50
    update = 100
    list = 200
    details = 300
    summarize_sub = 400
    summarize = 500
    enqueue = 600
    mark = 700
    unmark = 800
    download_queue = 900
    reload_config = 1000
