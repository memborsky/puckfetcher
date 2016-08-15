import copy
import logging
import os
import shutil
import tempfile

import umsgpack
import yaml

import puckfetcher.config as PC
import puckfetcher.subscription as PS


class TestConfig:
    @classmethod
    def setup_class(cls):

        # Mock XDG spec dirs to ensure we do the correct thing, and also that we don't put files in
        # strange places during testing.
        cls.old_environ = dict(os.environ)

        cls.default_config_dir = os.path.join(tempfile.mkdtemp(), "puckfetcher")
        cls.default_config_file = os.path.join(cls.default_config_dir, "config.yaml")

        cls.default_cache_dir = os.path.join(tempfile.mkdtemp(), "puckfetcher")

        cls.default_log_file = os.path.join(cls.default_cache_dir, "puckfetcher.log")
        logging.getLogger("root")

        cls.default_cache_file = os.path.join(cls.default_cache_dir, "puckcache")

        cls.default_data_dir = os.path.join(tempfile.mkdtemp(), "puckfetcher")

        cls.files = [cls.default_config_file, cls.default_log_file, cls.default_cache_file]

        cls.subscriptions = []
        for i in range(0, 3):
            name = "test" + str(i)
            url = "testurl" + str(i)
            directory = os.path.join(cls.default_data_dir, "dir" + str(i))

            sub = PS.Subscription(name=name, url=url, directory=directory)

            sub.download_backlog = True
            sub.backlog_limit = 1
            sub.use_title_as_filename = False

            cls.subscriptions.append(sub)

    @classmethod
    def teardown_class(cls):
        """Perform test cleanup."""
        shutil.rmtree(cls.default_config_dir)
        shutil.rmtree(cls.default_cache_dir)
        shutil.rmtree(cls.default_data_dir)

    # pylint: disable=invalid-name, no-self-use
    def test_default_config_assigns_files(self):
        """Test config with arguments assigns the right file vars."""
        config = _create_test_config()

        assert config.config_file == TestConfig.default_config_file
        assert config.cache_file == TestConfig.default_cache_file

    # pylint: disable=invalid-name, no-self-use
    def test_load_only_cache_loads_nothing(self):
        """If there are only subs in the cache, none in settings, discard them."""
        config = _create_test_config()

        write_msgpack_subs_to_file()

        config.load_state()

        assert config.cached_subscriptions == TestConfig.subscriptions
        assert config.subscriptions == []

    # pylint: disable=invalid-name, no-self-use
    def test_load_only_user_settings_works(self):
        """Test that settings can be loaded correctly from just the user settings."""
        config = _create_test_config()

        write_yaml_subs_to_file()

        config.load_state()

        assert config.cached_subscriptions == []
        assert config.subscriptions == TestConfig.subscriptions

    # pylint: disable=invalid-name, no-self-use
    def test_non_config_subs_ignore(self):
        """Subscriptions in cache but not config shouldn't be in subscriptions list."""
        config = _create_test_config()

        write_msgpack_subs_to_file()
        write_yaml_subs_to_file(subs=[TestConfig.subscriptions[0]])

        config.load_state()

        assert config.cached_subscriptions == TestConfig.subscriptions
        assert config.subscriptions == [TestConfig.subscriptions[0]]

    # pylint: disable=invalid-name, no-self-use
    def test_subscriptions_matching_works(self):
        """Subscriptions in cache should be matched to subscriptions in config by name or url."""
        config = _create_test_config()

        subs = _deep_copy_subs()

        write_yaml_subs_to_file(subs=subs)

        test_urls = ["bababba", "aaaaaaa", "ccccccc"]
        test_names = ["ffffff", "ggggg", "hhhhhh"]
        test_nums = [23, 555, 66666]

        # Change names and urls in subscriptions. They should be able to be matched to config
        # subscriptions.
        for i, sub in enumerate(subs):
            sub.feed_state.latest_entry_number = test_nums[i]

            if i % 2 == 0:
                sub.original_url = test_urls[i]
                sub.url = test_urls[i]
            else:
                sub.name = test_names[i]

            subs[i] = sub

        write_msgpack_subs_to_file(subs=subs)

        config.load_state()

        # The url and name the user gave should be prioritized and the cache url/name discarded.
        for i, sub in enumerate(config.subscriptions):
            if i % 2 == 0:
                assert sub.original_url != test_urls[i]
                assert sub.url != test_urls[i]
            else:
                assert sub.name != test_names[i]

            assert sub.feed_state.latest_entry_number == test_nums[i]

    # pylint: disable=no-self-use
    def test_save_works(self):
        """Test that we can save subscriptions correctly."""
        config = _create_test_config()

        config.subscriptions = TestConfig.subscriptions

        config.save_cache()

        with open(TestConfig.default_cache_file, "rb") as fff:
            contents = fff.read()
            subs = [PS.Subscription.decode_subscription(sub) for sub in umsgpack.unpackb(contents)]

        assert config.subscriptions == subs


# Helpers.
def _deep_copy_subs():
    return [copy.deepcopy(sub) for sub in TestConfig.subscriptions]


def _create_test_config():
    for created_file in TestConfig.files:
        if os.path.isfile(created_file):
            os.remove(created_file)

    return PC.Config(config_dir=TestConfig.default_config_dir,
                     cache_dir=TestConfig.default_cache_dir,
                     data_dir=TestConfig.default_data_dir)


def _ensure_file(out_file, default):
    # I don't like this, but it didn't seem like I could set keyword arguments to default to
    # class variables.
    if out_file is None:
        out_file = default

    directory, _ = os.path.split(out_file)
    if not os.path.exists(directory):
        os.makedirs(directory)

    return out_file


def write_msgpack_subs_to_file(out_file=None, subs=None):
    """Write subs to a file through msgpack."""

    out_file = _ensure_file(out_file, TestConfig.default_cache_file)

    if subs is None:
        subs = TestConfig.subscriptions

    encoded_subs = [PS.Subscription.encode_subscription(sub) for sub in subs]

    with open(out_file, "wb") as stream:
        packed = umsgpack.packb(encoded_subs)
        stream.write(packed)


def sub_to_user_yaml(sub):
    """Convert a subscription to YAML we expect to find in the users's config file."""
    # pylint: disable=protected-access
    return {"url": sub.original_url,
            "name": sub.name,
            "backlog_limit": sub.backlog_limit,
            "download_backlog": sub.download_backlog,
            "directory": sub.directory}


def write_yaml_subs_to_file(out_file=None, subs=None):
    """Write subscriptions in YAML to the config file."""
    out_file = _ensure_file(out_file, TestConfig.default_config_file)

    data = {}
    if subs is None:
        subs = TestConfig.subscriptions

    data["subscriptions"] = [sub_to_user_yaml(sub) for sub in subs]

    with open(out_file, "w") as stream:
        yaml.dump(data, stream)
