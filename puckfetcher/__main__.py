import argparse
import logging
from logging.handlers import RotatingFileHandler
import pkg_resources

import puckfetcher.config as C
import puckfetcher.util as U

VERSION = pkg_resources.require("puckfetcher")[0].version


def main():
    log_filename = U.get_xdg_cache_file_path("puckfetcher", "puckfetcher.log")

    formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(module)s - %(message)s")

    handler = RotatingFileHandler(filename=log_filename, maxBytes=1024000000, backupCount=10)
    handler.setFormatter(formatter)

    logger = logging.getLogger("root")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    logger.info("puckfetcher %s started!" % VERSION)

    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.")
    parser.add_argument("--config", dest="config", help="Location of config file.")
    args = parser.parse_args()

    config_file = vars(args)["config"]

    config = C.Config(config_file=config_file)

    subs = config.subscriptions
    while (True):
        try:
            for sub in subs:
                sub.get_feed()
                sub.attempt_update()

        # TODO look into replacing with
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        except KeyboardInterrupt:
            logger.critical("Received KeyboardInterrupt, exiting.")
            break

    parser.exit()

if __name__ == "__main__":
    main()
