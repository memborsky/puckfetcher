"""Tests for the config module."""
import copy
import os
from typing import Any, List, Tuple

import pytest
import umsgpack
import yaml

import puckfetcher.config as config
import puckfetcher.subscription as subscription


def test_default_config_construct(default_config: config.Config, default_conf_file: str,
                                  default_cache_file: str,
                                  ) -> None:
    """Test config with no arguments assigns the right file vars."""
    assert default_config.config_file == default_conf_file
    assert default_config.cache_file == default_cache_file


def test_load_only_cache(default_config: config.Config, default_cache_file: str,
                         subscriptions: List[subscription.Subscription],
                         ) -> None:
    """Subscriptions list should be empty if there are cached subs but no subs in settings."""
    write_subs_to_file(subs=subscriptions, out_file=default_cache_file, write_type="cache")

    default_config.load_state()

    assert default_config.subscriptions == []


def test_load_only_user_settings(default_config: config.Config, default_conf_file: str,
                                 subscriptions: List[subscription.Subscription],
                                 ) -> None:
    """Test that settings can be loaded correctly from just the user settings."""
    write_subs_to_file(subs=subscriptions, out_file=default_conf_file, write_type="config")

    default_config.load_state()

    assert default_config.subscriptions == subscriptions


def test_non_config_subs_ignore(default_config: config.Config, default_conf_file: str,
                                default_cache_file: str,
                                subscriptions: List[subscription.Subscription],
                                ) -> None:
    """Subscriptions in cache but not config shouldn't be in subscriptions list."""
    write_subs_to_file(subs=subscriptions, out_file=default_cache_file, write_type="cache")
    write_subs_to_file(subs=subscriptions[0:1], out_file=default_conf_file, write_type="config")

    default_config.load_state()

    assert default_config.subscriptions == subscriptions[0:1]


def test_subscriptions_matching(default_config: config.Config, default_conf_file: str,
                                default_cache_file: str,
                                subscriptions: List[subscription.Subscription],
                                ) -> None:
    """Subscriptions in cache should be matched to subscriptions in config by name or url."""
    write_subs_to_file(subs=subscriptions, out_file=default_conf_file, write_type="config")

    test_urls = ["bababba", "aaaaaaa", "ccccccc"]
    test_names = ["ffffff", "ggggg", "hhhhhh"]
    test_nums = [23, 555, 66666]

    # Change names and urls in subscriptions. They should be able to be matched to config
    # subscriptions.
    for i, sub in enumerate(subscriptions):
        sub.feed_state.latest_entry_number = test_nums[i]

        if i % 2 == 0:
            sub.original_url = test_urls[i]
            sub.url = test_urls[i]
        else:
            sub.metadata["name"] = test_names[i]

        subscriptions[i] = sub

    write_subs_to_file(subs=subscriptions, out_file=default_cache_file, write_type="cache")

    default_config.load_state()

    # The url and name the user gave should be prioritized and the cached url/name discarded.
    for i, sub in enumerate(default_config.subscriptions):
        if i % 2 == 0:
            assert sub.original_url != test_urls[i]
            assert sub.url != test_urls[i]
        else:
            assert sub.metadata["name"] != test_names[i]

        assert sub.feed_state.latest_entry_number == test_nums[i]


def test_save_works(default_config: config.Config, default_cache_file: str,
                    subscriptions: List[subscription.Subscription],
                    ) -> None:
    """Test that we can save subscriptions correctly."""
    default_config.subscriptions = subscriptions

    default_config.save_cache()

    with open(default_cache_file, "rb") as stream:
        contents = stream.read()
        unpacked_contents = umsgpack.unpackb(contents)
        subs = [subscription.Subscription.decode_subscription(sub) for sub in unpacked_contents]

    assert default_config.subscriptions == subs


def test_reload_config(default_config: config.Config, default_conf_file: str,
                                default_cache_file: str,
                                subscriptions: List[subscription.Subscription],
                                ) -> None:
    """Test that reloading gets us new settings."""
    write_subs_to_file(subs=subscriptions, out_file=default_cache_file, write_type="cache")
    write_subs_to_file(subs=subscriptions, out_file=default_conf_file, write_type="config")

    default_config.load_state()

    assert default_config.subscriptions == subscriptions

    new_subscriptions = copy.deepcopy(subscriptions)
    for sub in new_subscriptions:
        sub.metadata["artist"] = "foo"

    write_subs_to_file(subs=new_subscriptions, out_file=default_conf_file, write_type="config")

    default_config.load_state()

    assert default_config.subscriptions != subscriptions
    assert default_config.subscriptions == new_subscriptions


# Helpers.
def write_subs_to_file(subs: List[subscription.Subscription], out_file: str, write_type: str,
                      ) -> None:
    """Write subs to a file with the selected type."""

    if write_type == "cache":
        encoded_subs = [subscription.Subscription.encode_subscription(sub) for sub in subs]
        data = umsgpack.packb(encoded_subs)
        with open(out_file, "wb") as stream:
            stream.write(data)

    elif write_type == "config":
        data = {}
        data["subscriptions"] = [sub.as_config_yaml() for sub in subs]
        with open(out_file, "w", encoding="UTF-8") as stream2:
            yaml.dump(data, stream2)


# Fixtures.
@pytest.fixture(scope="function")
def config_dirs(tmpdir: Any) -> Tuple[str, str, str]:
    """Generate XDG dirs and vars."""
    config_dir = str(tmpdir.mkdir("config"))
    cache_dir = str(tmpdir.mkdir("cache"))
    data_dir = str(tmpdir.mkdir("data"))

    os.environ["XDG_CONFIG_HOME"] = config_dir
    os.environ["XDG_CACHE_DIR"] = cache_dir
    os.environ["XDG_DATA_DIR"] = data_dir

    return (config_dir, cache_dir, data_dir)


@pytest.fixture(scope="function")
def default_conf_file(config_dirs: Tuple[str, str, str]) -> str:
    """Provide name of default config file config object should use."""
    (config_dir, _, _) = config_dirs
    return os.path.join(config_dir, "config.yaml")


@pytest.fixture(scope="function")
def default_cache_file(config_dirs: Tuple[str, str, str]) -> str:
    """Provide name of default cache file config object should use."""
    (_, cache_dir, _) = config_dirs
    return os.path.join(cache_dir, "puckcache")


@pytest.fixture(scope="function")
def subscriptions(tmpdir: Any) -> List[subscription.Subscription]:
    """Generate subscriptions for config testing."""
    sub_dir = str(tmpdir.mkdir("foo"))

    subs = []
    for i in range(0, 3):
        name = "test" + str(i)
        url = "testurl" + str(i)
        directory = os.path.join(sub_dir, "dir" + str(i))

        sub = subscription.Subscription(name=name, url=url, directory=directory)

        sub.settings["backlog_limit"] = 1
        sub.settings["use_title_as_filename"] = False

        subs.append(sub)

    return subs


@pytest.fixture(scope="function")
def default_config(config_dirs: Tuple[str, str, str]) -> config.Config:
    """Create test config with temporary test dirs."""
    (config_dir, cache_dir, data_dir) = config_dirs

    return config.Config(config_dir=config_dir, cache_dir=cache_dir, data_dir=data_dir)
