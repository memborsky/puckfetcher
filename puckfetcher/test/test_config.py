import logging
import os
import shutil
import tempfile

import umsgpack

import puckfetcher.config as PC
import puckfetcher.subscription as PS


# TODO this needs reworking
class TestConfig:
    @classmethod
    def setup_class(cls):

        # Mock XDG spec dirs to ensure we do the correct thing, and also that we don't put files in
        # strange places during testing.
        cls.old_environ = dict(os.environ)

        cls.xdg_config_home = tempfile.mkdtemp()
        os.environ["XDG_CONFIG_HOME"] = cls.xdg_config_home
        cls.provided_config_dir = os.path.join(cls.xdg_config_home)
        cls.default_config_dir = os.path.join(cls.xdg_config_home, "puckfetcher")
        cls.default_config_file = os.path.join(cls.default_config_dir, "config.yaml")

        cls.xdg_cache_home = tempfile.mkdtemp()
        os.environ["XDG_CACHE_HOME"] = cls.xdg_cache_home
        cls.provided_cache_dir = os.path.join(cls.xdg_cache_home)
        cls.default_cache_dir = os.path.join(cls.xdg_cache_home, "puckfetcher")
        cls.default_log_file = os.path.join(cls.default_cache_dir, "puckfetcher.log")
        logging.getLogger("root")
        cls.default_cache_file = os.path.join(cls.default_cache_dir, "puckcache")

        cls.xdg_data_home = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = cls.xdg_data_home

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.xdg_config_home)
        shutil.rmtree(cls.xdg_cache_home)
        shutil.rmtree(cls.xdg_data_home)

    def check_config_created(self):
        """Test default config is created correctly."""

        with open(TestConfig.default_config_file) as f:
            actual = f.read()

        assert(actual == "")

    def test_creates_empty_config_file(self):
        """
        Constructing a config with a directory provided, but with no config file existing,
        should create the file.
        """

        config = PC.Config(config_dir=TestConfig.provided_config_dir)
        self.check_config_created()

    def test_save_cache_works(self):
        """Subscriptions should be saved correctly."""

        config = PC.Config(config_dir=TestConfig.provided_config_dir,
                           cache_dir=TestConfig.provided_cache_dir)

        sub = PS.Subscription(name="test", url="foo")

        config.subscriptions = [sub]

        config.save_cache()

        with open(TestConfig.default_cache_file, "rb") as f:
            bytestring = f.read()

            unpacked = umsgpack.unpackb(bytestring)
            unpacked_sub = PS.decode_subscription(unpacked[0])

            assert(unpacked_sub._provided_url == sub._provided_url)
            assert(unpacked_sub.name == sub.name)

    def test_load_state_works(self):
        """Subscriptions should be loaded correctly."""

        sub = PS.Subscription(name="test", url="foo")
        subs = [PS.encode_subscription(sub)]

        if not os.path.isdir(TestConfig.default_cache_dir):
            os.makedirs(TestConfig.default_cache_dir)
        with open(TestConfig.default_cache_file, "ab") as f:
            packed = umsgpack.packb(subs)
            f.write(packed)

        config = PC.Config(config_dir=TestConfig.provided_config_dir,
                           cache_dir=TestConfig.provided_cache_dir)

        expected_sub = sub
        actual_sub = config.cached_subscriptions[0]

        assert(actual_sub.name == expected_sub.name)
        assert(actual_sub._provided_url == expected_sub._provided_url)
