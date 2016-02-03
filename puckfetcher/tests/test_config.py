import os

import nose.tools as NT

import puckfetcher.config as C


def test_default_empty_config_load():
    """Load from default empty config file."""
    (file_dir, _) = os.path.split(os.path.realpath(__file__))
    config_dir = os.path.join(file_dir, "puckfetcher")
    config_file = os.path.join(config_dir, "config.yaml")

    # Save to re-export, though I think Python can't actually affect any other processes.
    old_xdg_config = os.environ["XDG_CONFIG_HOME"]
    os.environ["XDG_CONFIG_HOME"] = str(file_dir)

    C.Config()

    NT.assert_equal(os.path.isdir(config_dir), True)
    NT.assert_equal(os.path.isfile(config_file), True)

    os.remove(config_file)
    os.rmdir(config_dir)
    os.environ["XDG_CONFIG_HOME"] = old_xdg_config


def test_specified_empty_config_load():
    """Load from specified empty config file."""
    (file_dir, _) = os.path.split(os.path.realpath(__file__))
    config_file = os.path.join(file_dir, "nonexistentconfig.yaml")

    C.Config(config_file=config_file)

    NT.assert_equal(os.path.isfile(config_file), True)

    os.remove(config_file)


def test_non_default_config_populated_load():
    """Load from a populated config file."""
    (file_dir, _) = os.path.split(os.path.realpath(__file__))
    f = os.path.join(file_dir, "testconfig.yaml")

    config = C.Config(config_file=str(f))

    sub = config.subscriptions[0]

    NT.assert_equal(sub.name, "Test RSS Feed")
    NT.assert_equal(sub.provided_url, "https://andrewmichaud.com/rss.xml")
