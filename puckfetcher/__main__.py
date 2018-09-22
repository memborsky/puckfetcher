"""Main entry point for puckfetcher, used to repeatedly download podcasts from the command line."""
import argparse
import os
import sys
from logging import Logger
from typing import Any, Dict, List, Tuple

import drewtilities as util
from clint.textui import prompt

import puckfetcher.constants as constants
import puckfetcher.config as config
import puckfetcher.error as error

LOG: Logger

def main() -> None:
    """Run puckfetcher on the command line."""

    global LOG
    log_dir = constants.APPDIRS.user_log_dir
    log_filename = os.path.join(log_dir, f"{__package__}.log")
    LOG = util.set_up_logging(log_filename=log_filename, verbosity=constants.VERBOSITY)

    parser = _setup_program_arguments()
    args = parser.parse_args()

    (cache_dir, config_dir, data_dir) = _setup_directories(args)

    try:
        conf = config.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)
    except error.MalformedConfigError as exception:
        LOG.error("Unable to start puckfetcher - config error.")
        LOG.error(exception.desc)
        parser.exit()

    args = parser.parse_args()

    command_options = []
    config_commands = config.get_commands()
    for i, key in enumerate(config_commands):
        value = config_commands[key]
        command_options.append({"selector": str(i + 1), "prompt": value, "return": key.name})

    # See if we got a command-line command.
    config_dir = vars(args)["config"]
    command = vars(args)["command"]
    if command:
        if command == "menu":
            pass

        else:
            if command != "exit":
                _handle_command(command, conf)
            parser.exit()

    LOG.info(f"{__package__} {constants.VERSION} started!")

    while True:
        try:
            command = prompt.options("Choose a command", command_options)

            if command == "exit":
                parser.exit()

            _handle_command(command, conf)

        # TODO look into replacing with
        # https://stackoverflow.com/questions/1112343/how-do-i-capture-sigint-in-python
        except KeyboardInterrupt:
            LOG.critical("Received KeyboardInterrupt, exiting.")
            break

        except EOFError:
            LOG.critical("Received EOFError, exiting.")
            break

    parser.exit()

# TODO find a way to simplify and/or push logic into Config.
def _handle_command(command: str, conf: config.Config) -> None:
    try:
        if command == config.Command.update.name:
            conf.update()

        elif command == config.Command.list.name:
            conf.list()

        elif command == config.Command.summarize.name:
            conf.summarize()
            input("Press enter when done.")

        elif command == config.Command.details.name:
            sub_index = _choose_sub(conf)
            conf.details(sub_index)
            input("Press enter when done.")

        elif command == config.Command.summarize_sub.name:
            sub_index = _choose_sub(conf)
            conf.summarize_sub(sub_index)
            input("Press enter when done.")

        elif command == config.Command.download_queue.name:
            sub_index = _choose_sub(conf)
            conf.download_queue(sub_index)

        # TODO this needs work.
        elif command == config.Command.enqueue.name:
            (sub_index, entry_nums) = _sub_list_command_wrapper(conf, command)
            conf.enqueue(sub_index, entry_nums)

        elif command == config.Command.mark.name:
            (sub_index, entry_nums) = _sub_list_command_wrapper(conf, command)
            conf.mark(sub_index, entry_nums)

        elif command == config.Command.unmark.name:
            (sub_index, entry_nums) = _sub_list_command_wrapper(conf, command)
            conf.unmark(sub_index, entry_nums)

        elif command == config.Command.reload_config.name:
            conf.reload_config()

        else:
            LOG.error("Unknown command. Allowed commands are:")
            LOG.error(config.get_command_help())
            return

    except error.PuckError as e:
        LOG.error("Encountered error running command.")
        LOG.error(e.desc)


def _sub_list_command_wrapper(conf: config.Config, command: str) -> Tuple[int, List[int]]:
    sub_index = _choose_sub(conf)
    conf.details(sub_index)
    LOG.info(f"COMMAND - {command}")
    return (sub_index, _choose_entries())

def _choose_sub(conf: config.Config) -> int:
    sub_names = conf.get_subs()

    subscription_options = []
    pad_num = len(str(len(sub_names)))
    for i, sub_name in enumerate(sub_names):
        subscription_options.append(
            {"selector": str(i + 1).zfill(pad_num), "prompt": sub_name, "return": i})

    return prompt.options("Choose a subscription:", subscription_options)

def _choose_entries() -> List[int]:
    done = False
    while not done:
        num_string = input("Provide numbers of entries for this command."
                           "\nInvalid numbers will be ignored."
                           "\nPress enter with an empty line to go back to command menu.")

        if len(num_string) == 0:
            done = True
            num_list: List[int] = []
            break

        num_list = util.parse_int_string(num_string)

        while True:
            # TODO show ranges in what's shown here, for convenience. Still deduplicate.
            answer = input(f"Happy with {num_list}?"
                           "\n(If indices are too big/small, they'll be pulled out later.)"
                           "\n(No will let you try again)"
                           "\n[Yes/yes/y or No/no/n]")

            if len(answer) < 1:
                continue

            ans = answer.lower()[0]
            if ans == "y":
                done = True
                break

            elif ans == "n":
                break

    return num_list


# Helpers.
def _setup_directories(args: argparse.Namespace) -> Tuple[str, str, str]:
    config_dir = vars(args)["config"]
    if not config_dir:
        config_dir = constants.APPDIRS.user_config_dir

    cache_dir = vars(args)["cache"]
    if not cache_dir:
        cache_dir = constants.APPDIRS.user_cache_dir

    data_dir = vars(args)["data"]
    if not data_dir:
        data_dir = constants.APPDIRS.user_data_dir

    return (cache_dir, config_dir, data_dir)


def _setup_program_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download RSS feeds based on a config.",
                                     formatter_class=argparse.RawTextHelpFormatter)
    a = config.get_command_help()

    parser.add_argument("command",
                        help=(f"Command to run, one of:"
                              f"\n{a:<14}"))

    parser.add_argument("--cache", "-a", dest="cache",
                        help=(f"Cache directory to use. The '{__package__}' directory will be "
                              f"created here, and the 'puckcache' and '{__package__}.log' files "
                              f"will be stored there. '$XDG_CACHE_HOME' will be used if nothing "
                              f"is provided."))

    parser.add_argument("--config", "-c", dest="config",
                        help=(f" Config directory to use. The '{__package__}' directory will be "
                              f"created here. Put your 'config.yaml' file here to configure "
                              f"{__package__}. A default file will be created for you with "
                              f"default settings if you do not provide one. '$XDG_CONFIG_HOME' "
                              f" will be used if nothing is provided."))

    parser.add_argument("--data", "-d", dest="data",
                        help=("Data directory to use. Downloaded subscription entries will live "
                              "here. The 'directory' setting in the config file will also "
                              "affect the data directory, but this flag takes precedent. "
                              "'$XDG_DATA_HOME' will be used if nothing is provided."))

    parser.add_argument("--verbose", "-v", action="count",
                        help=("How verbose to be. If this is unused, only normal program output "
                              "will be logged. If there is one v, DEBUG output will be logged, "
                              "and logging will happen both to the log file and to stdout. If "
                              "there is more than one v, more debug output will happen. Some "
                              "things will never be logged no matter how much you vvvvvvvvvv."))

    parser.add_argument("--version", "-V", action="version",
                        version=f"{sys.argv[0]} {constants.VERSION}")

    return parser

if __name__ == "__main__":
    main()
