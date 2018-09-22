"""Tests for the __main__ module."""
from unittest.mock import MagicMock

import puckfetcher.__main__ as main

def test_simple_commands() -> None:
    """Test simple commands."""
    conf = MagicMock()

    # Mock config commands.
    conf.update = MagicMock()
    conf.list = MagicMock()

    # Test simple commands.
    main._handle_command("update", conf)
    main._handle_command("list", conf)
    main._handle_command("reload_config", conf)

    conf.update.assert_called_once_with()
    conf.list.assert_called_once_with()
    conf.reload_config.assert_called_once_with()

# TODO split these out
def test_list_commands() -> None:
    """Test commands that need a sub chosen from a list."""
    conf = MagicMock()

    conf.details = MagicMock()
    conf.download_queue = MagicMock()
    conf.enqueue = MagicMock()
    conf.mark = MagicMock()
    conf.unmark = MagicMock()

    # Test a command with a mocked sub choice.
    main._choose_sub = MagicMock(return_value=1)
    main._handle_command("download_queue", conf)

    conf.download_queue.assert_called_once_with(1)

    main._choose_sub = MagicMock(return_value=10000)
    main._handle_command("download_queue", conf)

    conf.download_queue.assert_called_with(10000)

    # Enqueue.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("enqueue", conf)
    conf.enqueue.assert_called_once_with(1, [1])

    # Mark.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("mark", conf)
    conf.mark.assert_called_once_with(1, [1])

    # Unmark.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("unmark", conf)
    conf.unmark.assert_called_once_with(1, [1])

    # TODO set up tests for summarize.

    # TODO restore fake command test
