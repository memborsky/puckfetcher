import argparse
import logging
from logging.handlers import RotatingFileHandler
from logging.handlers import StreamHandler
import os
import pkg_resources
import sys
import textwrap
import time

import puckfetcher.config as C
import puckfetcher.globals as G
import puckfetcher.util as U

# TODO find a better way to get puckfetcher.
G.PROGNAME = "puckfetcher"
G.VERSION = pkg_resources.require(G.PROGNAME)[0].version


def main():
    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.")

    parser.add_argument("--cache", "-a", dest="cache",
                        help=textwrap.dedent(
                            """\
                            Cache directory to use. The '{0}' directory will be created here, and
                            the 'puckcache' and 'puckfetcher.log' files will be stored there.
                            '$XDG_CACHE_HOME' will be used if nothing is provided.\
                            """.format(G.PROGNAME)))

    parser.add_argument("--config", "-c", dest="config",
                        help=textwrap.dedent(
                            """\
                            Config directory to use. The '{0}' directory will be created here. Put
                            your 'config.yaml' file here to configure {0}. A default file will be
                            created for you with default settings if you do not provide one.
                            '$XDG_CONFIG_HOME' will be used if nothing is provided.\
                            """.format(G.PROGNAME)))

    parser.add_argument("--data", "-d", dest="data",
                        help=textwrap.dedent(
                            """\
                            Data directory to use. The '{0}' directory will be created here. Put
                            your 'config.yaml' file here to configure {0}. A default file will be
                            created for you with default settings if you do not provide one.
                            The 'directory' setting in the config file will also affect the data
                            directory, but this flag takes precedent.
                            '$XDG_DATA_HOME' will be used if nothing is provided.
                            """.format(G.PROGNAME)))

    parser.add_argument("--verbose", "-v", action="count",
                        help=textwrap.dedent(
                            """\
                            How verbose to be. If this is unused, only normal program output will
                            be logged. If there is one v, DEBUG output will be logged, and logging
                            will happen both to the log file and to stdout. If there is more than
                            one v, more debug output will happen. Some things will never be logged
                            no matter how much you vvvvvvvvvv.
                            """.format(G.PROGNAME)))

    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {0}".format(G.VERSION))

    args = parser.parse_args()

    config_dir = vars(args)["config"]
    cache_dir = vars(args)["cache"]
    data_dir = vars(args)["data"]
    G.VERBOSITY = vars(args)["verbose"]

    if cache_dir is not None:
        log_filename = os.path.join(cache_dir, "{0}.log".format(G.PROGNAME))
    else:
        log_filename = U.get_xdg_cache_file_path("{0}".format(G.PROGNAME),
                                                 "{0}.log".format(G.PROGNAME))

    logger = logging.getLogger("root")

    formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(module)s - %(message)s")

    handler = RotatingFileHandler(filename=log_filename, maxBytes=1024000000, backupCount=10)
    handler.set_formatter(formatter)

    if G.VERBOSITY is None:
        logger.setLevel(logging.INFO)

    else:
        logger.setLevel(logging.DEBUG)

        stream_handler = StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.addHandler(handler)

    logger.info("{0} {1} started!".format(G.PROGNAME, G.VERSION))

    config = C.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)

    while (True):
        try:
            for i, sub in enumerate(config.subscriptions):
                logger.debug("working on {0}".format(i))
                logger.debug("sub contents {0}".format(sub))
                sub.attempt_update()
                config.subscriptions[i] = sub

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
