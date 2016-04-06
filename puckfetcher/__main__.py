"""Main entry point for puckfetcher, used to repeatedly download podcasts from the command line."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import textwrap
from argparse import RawTextHelpFormatter
from enum import Enum

from clint.textui import prompt

import puckfetcher.constants as CONSTANTS
import puckfetcher.config as C


def main():
    """Run puckfetcher on the command line."""

    parser = _setup_program_arguments()
    args = parser.parse_args()

    (cache_dir, config_dir, data_dir, log_dir) = _setup_directories(args)

    logger = _setup_logging(log_dir)

    config = C.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)

    # See if we got a command-line command.
    config_dir = vars(args)["config"]
    command = vars(args)["command"]
    if command:
        print(command)
        if command == _Command.exit.name:
            _handle_requested_exit(parser, logger)

        elif command == _Command.prompt.name:
            pass

        else:
            # TODO do something cleaner than passing all this to handle_command.
            _handle_command(command, config)
            _handle_elective_exit(parser)


    logger.info("%s %s started!", __package__, CONSTANTS.VERSION)

    # TODO push the command implementations into Config. Eventually make that an API.
    # TODO CLI should probably print and not log.
    while True:
        try:
            command_options = [{"selector": "1",
                                "prompt": "Exit.",
                                "return": _Command.exit.name},
                               {"selector": "2",
                                "prompt": "Update subscriptions once.",
                                "return": _Command.update_once.name},
                               {"selector": "3",
                                "prompt": "Update subscriptions continuously.",
                                "return": _Command.update_forever.name},
                               {"selector": "4",
                                "prompt": "Load/reload subscriptions configuration.",
                                "return": _Command.load.name},
                               {"selector": "5",
                                "prompt": "List current subscriptions.",
                                "return": _Command.list.name}]

            command = prompt.options("Choose a command", command_options)
            # TODO wrap in something nicer, we don't want to show _Command.EXIT.
            logger.info("Chose: %s", command)

            if command == _Command.exit.name:
                _handle_requested_exit(parser)

            _handle_command(command, config)


        # TODO look into replacing with
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        except KeyboardInterrupt:
            logger.critical("Received KeyboardInterrupt, exiting.")
            break

        except EOFError:
            logger.critical("Received EOFError, exiting.")
            break

    parser.exit()


# TODO maybe reorganize helper functions?? Not sure what to do, but this looks messy.
# Theoretically this would do cleanup if we needed to do any.
def _handle_requested_exit(parser):
    print("Told to exit, exiting.")
    parser.exit()

def _handle_elective_exit(parser):
    print("Exiting.")
    parser.exit()


def _handle_command(command, config):
    # TODO use config exit status to return exit codes.
    if command == _Command.update_once.name:
        config.update_once()


    elif command == _Command.update_forever.name:
        config.update_forever()

    elif command == _Command.load.name:
        load_successful = config.load_state()
        if load_successful:
            print("Reloaded config successfully!")

        else:
            print("Did not reload config successfully!")

    # TODO provide more information, possibly hidden behind more command line operations.
    elif command == _Command.list.name:
        config.list()

    else:
        print("Unknown command!")


def _setup_directories(args):
    config_dir = vars(args)["config"]
    if not config_dir:
        config_dir = CONSTANTS.APPDIRS.user_config_dir

    cache_dir = vars(args)["cache"]
    if not cache_dir:
        cache_dir = CONSTANTS.APPDIRS.user_cache_dir
        log_dir = CONSTANTS.APPDIRS.user_log_dir
    else:
        log_dir = os.path.join(cache_dir, "log")

    data_dir = vars(args)["data"]
    if not data_dir:
        data_dir = CONSTANTS.APPDIRS.user_data_dir

    return (cache_dir, config_dir, data_dir, log_dir)


def _setup_program_arguments():
    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.",
                                     formatter_class=RawTextHelpFormatter)

    parser.add_argument("command", metavar="command", type=str,
                        help=textwrap.dedent(
                            """\
                            Command to run, one of:
                            update_once - update all subscriptions once
                            update_forever - update all subscriptions in a loop until terminated
                            load - (re)load configuration (currently useless from shell...)
                            list - list current subscriptions, after reloading config
                            prompt - go to a prompt to choose option\
                            """))

    parser.add_argument("--cache", "-a", dest="cache",
                        help=textwrap.dedent(
                            """\
                            Cache directory to use. The '{0}' directory will be created here, and
                            the 'puckcache' and '{0}.log' files will be stored there.
                            '$XDG_CACHE_HOME' will be used if nothing is provided.\
                            """.format(__package__)))

    parser.add_argument("--config", "-c", dest="config",
                        help=textwrap.dedent(
                            """\
                            Config directory to use. The '{0}' directory will be created here. Put
                            your 'config.yaml' file here to configure {0}. A default file will be
                            created for you with default settings if you do not provide one.
                            '$XDG_CONFIG_HOME' will be used if nothing is provided.\
                            """.format(__package__)))

    parser.add_argument("--data", "-d", dest="data",
                        help=textwrap.dedent(
                            """\
                            Data directory to use. The '{0}' directory will be created here. Put
                            your 'config.yaml' file here to configure {0}. A default file will be
                            created for you with default settings if you do not provide one.
                            The 'directory' setting in the config file will also affect the data
                            directory, but this flag takes precedent.
                            '$XDG_DATA_HOME' will be used if nothing is provided.
                            """.format(__package__)))

    parser.add_argument("--verbose", "-v", action="count",
                        help=textwrap.dedent(
                            """\
                            How verbose to be. If this is unused, only normal program output will
                            be logged. If there is one v, DEBUG output will be logged, and logging
                            will happen both to the log file and to stdout. If there is more than
                            one v, more debug output will happen. Some things will never be logged
                            no matter how much you vvvvvvvvvv.
                            """.format(__package__)))

    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {0}".format(CONSTANTS.VERSION))

    return parser


def _setup_logging(log_dir):
    log_filename = os.path.join(log_dir, "{0}.log".format(__package__))

    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)

    if not os.path.isfile(log_filename):
        open(log_filename, 'a').close()

    logger = logging.getLogger("root")

    formatter = logging.Formatter(fmt="%(asctime)s - %(levelname)s - %(module)s - %(message)s")

    handler = RotatingFileHandler(filename=log_filename, maxBytes=1024000000, backupCount=10)
    handler.setFormatter(formatter)

    if CONSTANTS.VERBOSITY == 0:
        logger.setLevel(logging.INFO)

    else:
        logger.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.addHandler(handler)

    return logger


class _Command(Enum):
    exit = 0
    prompt = 1
    update_once = 2
    update_forever = 3
    load = 4
    list = 5


if __name__ == "__main__":
    main()
