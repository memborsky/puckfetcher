import os

import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S
import puckfetcher.util as U


class Config():
    """Class holding config options."""

    def __init__(self, config_file=None):
        self.config_file = config_file
        self.load_config()
        if self.settings is not None:
            self.parse_subscriptions()

    def load_config(self):
        """Load config file."""
        if self.config_file is None:
            self.config_file = U.get_xdg_config_dir_path("puckfetcher", "config.yaml")

        (config_dir, _) = os.path.split(self.config_file)

        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        if not os.path.exists(self.config_file):
            with open(self.config_file, "w") as stream:
                # TODO write default options
                stream.write("# Created by puckfetcher")
            self.settings = None
            return

        else:
            with open(self.config_file, "r") as stream:
                self.settings = yaml.load(stream)
                print("settings: {0}".format(self.settings))

    def parse_subscriptions(self):
        """Parse subscriptions from config file."""
        self.subscriptions = []
        for sub_yaml_index in range(len(self.settings["subscriptions"])):
            sub_yaml = self.settings["subscriptions"][sub_yaml_index]

            if sub_yaml["name"] is None:
                name = "Generic Podcast {0}".format(sub_yaml_index)
            else:
                name = sub_yaml["name"]

            if sub_yaml["url"] is None:
                raise E.InvalidConfigError("No URL provide, URL is mandatory!")
            else:
                url = sub_yaml["url"]

            sub = S.Subscription(name=name, url=url)
            self.subscriptions.append(sub)
