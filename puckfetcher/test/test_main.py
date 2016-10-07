# -*- coding: utf-8 -*-
"""Tests for the __main__ module."""
# NOTE - Python 2 shim.
from __future__ import unicode_literals

# NOTE - Python 2 shim.
# pylint: disable=redefined-builtin
from builtins import input

try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

import puckfetcher.__main__ as main
import puckfetcher.config as Config

def test_simple_commands():
    """Test simple commands."""
    config = Config.Config.__new__(Config.Config)

    # Mock config commands.
    config.update = MagicMock()
    config.list = MagicMock()

    # Test simple commands.
    main._handle_command("update", config, None, None)
    main._handle_command("list", config, None, None)

    config.update.assert_called_once_with()
    config.list.assert_called_once_with()

def test_list_commands():
    """Test commands that need a sub chosen from a list."""
    config = Config.Config.__new__(Config.Config)


    config.details = MagicMock()
    config.download_queue = MagicMock()
    config.enqueue = MagicMock()
    config.mark = MagicMock()
    config.unmark = MagicMock()

    # Test a command with a mocked sub choice.
    main._choose_sub = MagicMock(return_value=1)
    main._handle_command("download_queue", config, None, None)

    config.download_queue.assert_called_once_with(1)

    main._choose_sub = MagicMock(return_value=10000)
    main._handle_command("download_queue", config, None, None)

    config.download_queue.assert_called_with(10000)

    # Enqueue.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("enqueue", config, None, None)
    config.enqueue.assert_called_once_with(1, [1])

    # Mark.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("mark", config, None, None)
    config.mark.assert_called_once_with(1, [1])

    # Unmark.
    main._sub_list_command_wrapper = MagicMock(return_value=(1, [1]))
    main._handle_command("unmark", config, None, None)
    config.unmark.assert_called_once_with(1, [1])

    log = MagicMock()
    log.error = MagicMock()

    log.error.assert_not_called()

    fake_command_options = [{"return": "foo", "prompt": "bar"},
                            {"return": "foo", "prompt": "bar"},
                            {"return": "foo", "prompt": "bar"},
                            {"return": "foo", "prompt": "bar"}]

    main._handle_command("adsf", None, fake_command_options, log)

    log.error.call_count = 6
