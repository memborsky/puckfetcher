import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import pkg_resources
import time

import puckfetcher.config as C
import puckfetcher.util as U

# TODO find a better way to get puckfetcher.
PROGNAME = "puckfetcher"
VERSION = pkg_resources.require(PROGNAME)[0].version


def main():
    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.")
    parser.add_argument("--cache", "-a", dest="cache", help="Cache directory to use.")
    parser.add_argument("--config", "-c", dest="config", help="Config directory to use.")
    parser.add_argument("--data", "-d", dest="data", help="User data directory to use.")
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {0}".format(VERSION))
    args = parser.parse_args()

    config_dir = vars(args)["config"]
    cache_dir = vars(args)["cache"]
    data_dir = vars(args)["data"]
    verbose = vars(args)["verbose"]

    if cache_dir is not None:
        log_filename = os.path.join(cache_dir, "{0}.log".format(PROGNAME))
    else:
        log_filename = U.get_xdg_cache_file_path("{0}".format(PROGNAME),
                                                 "{0}.log".format(PROGNAME))

    formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(module)s - %(message)s")

    handler = RotatingFileHandler(filename=log_filename, maxBytes=1024000000, backupCount=10)
    handler.setFormatter(formatter)

    logger = logging.getLogger("root")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)

    logger.info("{0} {1} started!".format(PROGNAME, VERSION))

    config = C.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)

    subs = config.subscriptions
    while (True):
        try:
            for i, sub in enumerate(subs):
                logger.debug("working on {0}".format(i))
                logger.debug("sub contents {0}".format(sub))
                sub.attempt_update()
                subs[i] = sub

                config.save_cache()

            time.sleep(5)

        # TODO look into replacing with
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        except KeyboardInterrupt:
            logger.critical("Received KeyboardInterrupt, exiting.")
            break

    parser.exit()

if __name__ == "__main__":
    main()
