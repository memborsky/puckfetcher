import os

import nose.tools as NT

import puckfetcher.config as C
import puckfetcher.util as U


def test_default_config_empty_load():
    """Load from default empty config file."""
    f = U.get_xdg_config_dir_path("puckfetcher", "config.yaml")
    config = C.Config()
    print(config.settings)
    NT.assert_equal(config.settings, None)
    os.remove(f)


def test_non_default_config_empty_load():
    """Load from default empty config file."""
    (file_dir, _) = os.path.split(os.path.realpath(__file__))
    f = os.path.join(file_dir, "nonexistentconfig.yaml")
    config = C.Config(config_file=f)
    NT.assert_equal(config.settings, None)
    os.remove(f)


def test_non_default_config_populated_load():
    """Load from a populated config file."""
    (file_dir, _) = os.path.split(os.path.realpath(__file__))
    f = os.path.join(file_dir, "testconfig.yaml")
    print(str(f))
    config = C.Config(config_file=str(f))
    sub = config.subscriptions[0]
    NT.assert_equal(sub.name, "Test RSS Feed")
    NT.assert_equal(sub.provided_url, "https://andrewmichaud.com/rss.xml")
