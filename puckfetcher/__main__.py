"""Main entry point for puckfetcher, used to repeatedly download podcasts from the command line."""

import argparse
from argparse import RawTextHelpFormatter
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import textwrap
from enum import Enum

from clint.textui import prompt

import puckfetcher.constants as CONSTANTS
import puckfetcher.config as Config
import puckfetcher.util as Util

try:
    rawest_input = raw_input
except NameError:
    rawest_input = input


# TODO consolidate printing and logging into one log handler.
# 'logs' to stdout shouldn't hove date/time stuff and should only be info level or above, unless
# the user told us to be verbose.
def main():
    """Run puckfetcher on the command line."""

    parser = _setup_program_arguments()
    args = parser.parse_args()

    (cache_dir, config_dir, data_dir, log_dir) = _setup_directories(args)

    logger = _setup_logging(log_dir)

    config = Config.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)

    index = 1
    command_options = [{"selector": str(index), "prompt": "Exit.", "return": _Command.exit.name}]

    index += 1
    config_commands = config.get_commands()
    for key in config_commands.keys():
        value = config.commands[key]
        command_options.append({"selector": str(index), "prompt": value, "return": key.name})
        index += 1

    # See if we got a command-line command.
    config_dir = vars(args)["config"]
    command = vars(args)["command"]
    if command:
        if command == _Command.exit.name:
            _handle_exit(parser)

        elif command == _Command.prompt.name:
            pass

        else:
            # TODO do something cleaner than passing all this to handle_command.
            _handle_command(command, config, command_options)
            _handle_exit(parser)

    logger.info("%s %s started!", __package__, CONSTANTS.VERSION)

    # TODO CLI should probably print and not log.
    while True:
        try:
            command = prompt.options("Choose a command", command_options)

            if command == _Command.exit.name:
                _handle_exit(parser)

            _handle_command(command, config, command_options)

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
def _handle_exit(parser):
    parser.exit()

def _handle_command(command, config, command_options):
    # TODO use config exit status to return exit codes.
    if command == Config.Command.update_once.name:
        (res, msg) = config.update_once()

    elif command == Config.Command.update_forever.name:
        (res, msg) = config.update_forever()

    elif command == Config.Command.load.name:
        (res, msg) = config.load_state()

    elif command == Config.Command.list.name:
        (res, msg) = config.list()

    elif command == Config.Command.details.name:
        sub_index = _choose_sub(config)
        (res, msg) = config.details(sub_index)
        input("Press enter when done.")

    elif command == Config.Command.enqueue.name:
        sub_index = _choose_sub(config)

        done = False
        while not done:
            num_string = rawest_input(textwrap.dedent(
                """
                Provide numbers of entries to put in download queue.
                Invalid numbers will be ignored.
                Press enter with an empty line to go back to command menu.
                """))

            if len(num_string) == 0:
                done = True
                (res, msg) = (False, "Canceled enqueuing")
                break

            num_list = Util.parse_int_string(num_string)

            while True:
                answer = rawest_input(textwrap.dedent(
                    """\
                    Happy with {}?
                    (If indices are too big/small, they'll be pulled out later.)
                    (No will let you try again)
                    [Yes/yes/y or No/no/n]
                    """.format(num_list)))

                if len(answer) < 1:
                    continue

                ans = answer.lower()[0]
                if ans == "y":
                    (res, msg) = config.enqueue(sub_index, num_list)
                    done = True
                    break

                elif ans == "n":
                    break

    elif command == Config.Command.download_queue.name:
        sub_index = _choose_sub(config)
        (res, msg) = config.download_queue(sub_index)

    else:
        print("Unknown command!")
        print("Allowed commands:")
        for command in command_options:
            print("    {}: {}".format(command["return"], command["prompt"]))
        return

    if not res:
        print(msg)

def _choose_sub(config):
    sub_names = config.get_subs()
    subscription_options = []
    for i, sub_name in enumerate(sub_names):
        subscription_options.append({"selector": str(i+1), "prompt": sub_name, "return": i})

    return prompt.options("Choose a subscription:", subscription_options)


# Helpers.
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
                            """))

    parser.add_argument("--version", "-V", action="version",
                        version="%(prog)s {}".format(CONSTANTS.VERSION))

    return parser


def _setup_logging(log_dir):
    log_filename = os.path.join(log_dir, "{}.log".format(__package__))

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


if __name__ == "__main__":
    main()
