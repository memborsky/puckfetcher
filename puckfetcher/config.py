import logging
import os
import textwrap

import yaml

import puckfetcher.error as E
import puckfetcher.subscription as S
import puckfetcher.util as U

logger = logging.getLogger("root")


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
            config_dir = U.get_xdg_config_dir_path("puckfetcher")
            self.config_file = os.path.join(config_dir, "config.yaml")
            logger.info("No config file provided, using default {0}.".format(self.config_file))

        else:
            config_dir, _ = os.path.split(self.config_file)
            if not os.path.exists(config_dir):
                logger.debug("Config directory {0} does not exist, creating.".format(config_dir))
                os.makedirs(config_dir)
            logger.info("Using provided config file {0}.".format(self.config_file))

        if not os.path.exists(self.config_file):
            logger.debug(textwrap.dedent(
                """
                Config file {0} does not exist, creating file with default settings.
                """.format(self.config_file)))

            with open(self.config_file, "w") as stream:
                # TODO write default options
                stream.write("# Created by puckfetcher")

        with open(self.config_file, "r") as stream:
            logger.info("Opening config file to retrieve settings.")
            self.settings = yaml.load(stream)

        logger.debug(textwrap.dedent(
            """
            Full Retrieved settings:
            {0}
            """.format(yaml.dump(self.settings, width=1, indent=4))))

    def parse_subscriptions(self):
        """Parse subscriptions from config file."""
        self.subscriptions = []
        for i, sub_yaml in enumerate(self.settings["subscriptions"]):
            logger.info("Parsing subscription number {0}.".format(i))

            if sub_yaml["name"] is None:
                name = "Generic Podcast {0}".format(i)
            else:
                name = sub_yaml["name"]

            if sub_yaml["url"] is None:
                raise E.InvalidConfigError("No URL provided, URL is mandatory!")
            else:
                url = sub_yaml["url"]

            download_backlog = sub_yaml.get("download_backlog", True)
            backlog_limit = sub_yaml.get("backlog_limit", None)

            logger.debug(textwrap.dedent(
                """
                Parsed subscription:
                name: {0}
                url: {1}
                download_backlog: {2}
                backlog_limit: {3}
                """.format(name, url, download_backlog, backlog_limit)))

            sub = S.Subscription(name=name, url=url, download_backlog=download_backlog,
                                 backlog_limit=backlog_limit)

            # TODO add ability to pretty-print subscription and print here.
            self.subscriptions.append(sub)
