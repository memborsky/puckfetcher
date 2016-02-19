import logging
import os
import shutil
import tempfile

import msgpack

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
        cls.default_config_dir = os.path.join(cls.xdg_config_home, "puckfetcher")
        cls.default_config_file = os.path.join(cls.default_config_dir, "config.yaml")

        cls.xdg_cache_home = tempfile.mkdtemp()
        os.environ["XDG_CACHE_HOME"] = cls.xdg_cache_home
        cls.default_cache_dir = os.path.join(cls.xdg_cache_home, "puckfetcher")
        cls.default_log_file = os.path.join(cls.default_cache_dir, "puckfetcher.log")
        logging.getLogger("root")
        cls.default_cache_file = os.path.join(cls.default_cache_dir, "puckcache")

        cls.xdg_data_home = tempfile.mkdtemp()
        os.environ["XDG_DATA_HOME"] = cls.xdg_data_home

    @classmethod
    def teardown_class(cls):
        os.environ.clear()
        os.environ.update(cls.old_environ)

        shutil.rmtree(cls.xdg_config_home)
        shutil.rmtree(cls.xdg_cache_home)
        shutil.rmtree(cls.xdg_data_home)

    def check_config_created(self):
        """Test default config is created correctly."""
        assert(os.path.isdir(TestConfig.default_config_dir) is True)
        assert(os.path.isfile(TestConfig.default_config_file) is True)

        with open(TestConfig.default_config_file) as f:
            actual = f.read()
            example_config = os.path.join(os.path.dirname(__file__), "..", "example_config.yaml")
            with open(example_config, "r") as g:
                expected = g.read()
                assert(actual == expected)

    def test_no_directory_creates_xdg_config_file(self):
        """
        Constructing a config with no directory provided should create a config file in the
        XDG_CONFIG_HOME directory.
        """

        PC.Config()
        self.check_config_created()

    def test_creates_empty_config_file(self):
        """
        Constructing a config with a directory provided, but with no config file existing,
        should create the file.
        """

        PC.Config(config_dir=TestConfig.default_config_dir)
        self.check_config_created()

    def test_save_cache_works(self):
        """Subscriptions should be saved correctly."""

        config = PC.Config(config_dir=TestConfig.default_config_dir,
                           cache_dir=TestConfig.default_cache_dir)

        sub = PS.Subscription(name="test", url="foo")

        config.subscriptions = [sub]

        config.save_cache()

        with open(TestConfig.default_cache_file, "rb") as f:
            bytestring = f.read()

            unpacked = msgpack.unpackb(bytestring, object_hook=PS.decode_subscription)
            unpacked_sub = unpacked[0]

            assert(unpacked_sub._provided_url == sub._provided_url)
            assert(unpacked_sub.name == sub.name)

    def test_load_state_works(self):
        """Subscriptions should be loaded correctly."""

        subs = [PS.Subscription(name="test", url="foo")]

        with open(TestConfig.default_cache_file, "wb") as f:
            packed = msgpack.packb(subs, default=PS.encode_subscription)
            f.write(packed)

        config = PC.Config(config_dir=TestConfig.default_config_dir,
                           cache_dir=TestConfig.default_cache_dir)

        config.load_state()

        sub = subs[0]

        assert(config.subscriptions[0].name == sub.name)
        assert(config.subscriptions[0]._provided_url == sub._provided_url)
