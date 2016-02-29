import copy
import logging
import os
import shutil
import tempfile

import umsgpack
import yaml

import puckfetcher.config as PC
import puckfetcher.subscription as PS


# TODO this needs reworking
class TestConfig:
    @classmethod
    def setup_class(cls):

        # Mock XDG spec dirs to ensure we do the correct thing, and also that we don't put files in
        # strange places during testing.
        cls.old_environ = dict(os.environ)

        cls.provided_config_dir = tempfile.mkdtemp()
        cls.default_config_dir = os.path.join(cls.provided_config_dir, "puckfetcher")
        cls.default_config_file = os.path.join(cls.default_config_dir, "config.yaml")

        cls.provided_cache_dir = tempfile.mkdtemp()
        cls.default_cache_dir = os.path.join(cls.provided_cache_dir, "puckfetcher")

        cls.default_log_file = os.path.join(cls.default_cache_dir, "puckfetcher.log")
        logging.getLogger("root")

        cls.default_cache_file = os.path.join(cls.default_cache_dir, "puckcache")

        cls.provided_data_dir = tempfile.mkdtemp()

        cls.files = [cls.default_config_file, cls.default_log_file, cls.default_cache_file]

        cls.sub1 = PS.Subscription(name="test1", url="foo")
        cls.sub2 = PS.Subscription(name="test2", url="bar")
        cls.sub3 = PS.Subscription(name="test3", url="baz")

        cls.subscriptions = [cls.sub1, cls.sub2, cls.sub3]

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.provided_config_dir)
        shutil.rmtree(cls.provided_cache_dir)
        shutil.rmtree(cls.provided_data_dir)

    def create_test_config(self):
        """Create test config with test dirs."""
        for f in TestConfig.files:
            if os.path.isfile(f):
                os.remove(f)

        return PC.Config(config_dir=TestConfig.provided_config_dir,
                         cache_dir=TestConfig.provided_cache_dir,
                         data_dir=TestConfig.provided_data_dir)

    def write_msgpack_subs_to_file(self, out_file=None, subs=None):
        """Write subs to a file through msgpack."""

        # I don't like this, but it didn't seem like I could set keyword arguments to default to
        # class variables.
        if out_file is None:
            out_file = TestConfig.default_cache_file

        if subs is not None:
            encoded_subs = list(map(PS.encode_subscription, subs))
        else:
            encoded_subs = list(map(PS.encode_subscription, TestConfig.subscriptions))

        d, _ = os.path.split(out_file)
        if not os.path.exists(d):
            os.makedirs(d)

        with open(out_file, "wb") as f:
            packed = umsgpack.packb(encoded_subs)
            f.write(packed)

    def write_yaml_subs_to_file(self, out_file=None, subs=None):
        """Write subscriptions in YAML to the config file."""

        if out_file is None:
            out_file = TestConfig.default_config_file

        data = {}
        if subs is None:
            subs = TestConfig.subscriptions

        data["subscriptions"] = []
        for i, sub in enumerate(subs):
            d = {}
            d["url"] = sub._provided_url
            d["name"] = sub.name
            if sub.backlog_limit is not None:
                d["backlog_limit"] = sub.backlog_limit
            d["download_backlog"] = sub.download_backlog

            data["subscriptions"].append(d)

        d, _ = os.path.split(out_file)
        if not os.path.exists(d):
            os.makedirs(d)

        with open(out_file, "w") as f:
            yaml.dump(data, f)

    def test_default_config_assigns_files(self):
        """Test config with arguments assigns the right file vars."""
        config = self.create_test_config()

        assert(config.config_file == TestConfig.default_config_file)
        assert(config.cache_file == TestConfig.default_cache_file)

    def test_load_only_cache_loads_nothing(self):
        """If there are only subs in the cache, none in settings, discard them."""
        config = self.create_test_config()

        self.write_msgpack_subs_to_file()

        config.load_state()

        assert(config.cached_subscriptions == TestConfig.subscriptions)
        assert(config.subscriptions == [])

    def test_load_only_user_settings_works(self):
        """Test that settings can be loaded correctly from just the user settings."""
        config = self.create_test_config()

        self.write_yaml_subs_to_file()

        config.load_state()

        assert(config.cached_subscriptions == [])
        assert(config.subscriptions == TestConfig.subscriptions)

    def test_non_config_subs_ignore(self):
        """Subscriptions in cache but not config shouldn't be in subscriptions list."""
        config = self.create_test_config()

        self.write_msgpack_subs_to_file()
        self.write_yaml_subs_to_file(subs=[TestConfig.sub1])

        config.load_state()

        assert(config.cached_subscriptions == TestConfig.subscriptions)
        assert(config.subscriptions == [TestConfig.sub1])

    def test_subscriptions_matched_by_name(self):
        """Subscriptions in cache should be matched to subscriptions in config by name."""
        config = self.create_test_config()

        subs = [copy.deepcopy(TestConfig.sub1),
                copy.deepcopy(TestConfig.sub2),
                copy.deepcopy(TestConfig.sub3)]

        self.write_yaml_subs_to_file(subs=subs)

        test_urls = ["bababba", "aaaaaaa", "ccccccc"]
        test_nums = [1999, 24, 777]

        # Change urls and latest entry numbers in subscriptions.
        # The urls shouldn't make it through (the urls in user settings will be prioritized), but
        # the latest entry numbers should make it.
        # The settings/cache merge code should be able to match these subs even if the urls have
        # changed, as long as the names are the same.
        for i, sub in enumerate(subs):
            sub._provided_url = test_urls[i]
            sub.latest_entry_number = test_nums[i]
            subs[i] = sub

        self.write_msgpack_subs_to_file(subs=subs)

        config.load_state()

        for i, sub in enumerate(config.subscriptions):
            assert(sub._provided_url != test_urls[i])
            assert(sub._current_url != test_urls[i])

            assert(sub.latest_entry_number == test_nums[i])

    def test_subscriptions_matched_by_url(self):
        """Subscriptions in cache should be matched to subscriptions in config by url."""
        config = self.create_test_config()

        subs = [copy.deepcopy(TestConfig.sub1),
                copy.deepcopy(TestConfig.sub2),
                copy.deepcopy(TestConfig.sub3)]

        self.write_yaml_subs_to_file(subs=subs)

        test_names = ["bababba", "aaaaaaa", "ccccccc"]
        test_urls = ["bababba", "aaaaaaa", "ccccccc"]
        test_nums = [1999, 24, 777]

        # Change urls and latest entry numbers in subscriptions.
        # The urls shouldn't make it through (the urls in user settings will be prioritized), but
        # the latest entry numbers should make it.
        # The settings/cache merge code should be able to match these subs even if the names have
        # changed, as long as the urls are the same.
        for i, sub in enumerate(subs):
            sub.name = test_names[i]
            sub.latest_entry_number = test_nums[i]
            subs[i] = sub

        self.write_msgpack_subs_to_file(subs=subs)

        config.load_state()

        for i, sub in enumerate(config.subscriptions):
            assert(sub._provided_url != test_urls[i])
            assert(sub._current_url != test_urls[i])

            assert(sub.latest_entry_number == test_nums[i])
