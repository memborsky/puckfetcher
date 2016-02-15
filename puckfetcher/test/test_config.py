import shutil
import os
import tempfile

import msgpack

import puckfetcher.config as PC
import puckfetcher.subscription as PS


# TODO this needs reworking
class TestConfig:
    @classmethod
    def setup_class(cls):
        cls.xdg_config_home = tempfile.mkdtemp()
        cls.old_xdg_config_home = os.environ.get("XDG_CONFIG_HOME", None)
        os.environ["XDG_CONFIG_HOME"] = cls.xdg_config_home

        cls.xdg_cache_home = tempfile.mkdtemp()
        cls.old_xdg_cache_home = os.environ.get("XDG_CACHE_HOME", None)
        os.environ["XDG_CACHE_HOME"] = cls.xdg_cache_home

        cls.xdg_data_home = tempfile.mkdtemp()
        cls.old_xdg_data_home = os.environ.get("XDG_DATA_HOME", None)
        os.environ["XDG_DATA_HOME"] = cls.xdg_data_home

    @classmethod
    def teardown_class(cls):
        os.environ["XDG_CONFIG_HOME"] = cls.old_xdg_config_home
        os.environ["XDG_CACHE_HOME"] = cls.old_xdg_cache_home
        os.environ["XDG_DATA_HOME"] = cls.old_xdg_data_home

        shutil.rmtree(cls.xdg_config_home)
        shutil.rmtree(cls.xdg_cache_home)
        shutil.rmtree(cls.xdg_data_home)

    def test_no_directory_creates_xdg_config_file(self):
        """
        Constructing a config with no directory provided should create a config file in the
        XDG_CONFIG_HOME directory.
        """

        directory = os.path.join(TestConfig.xdg_config_home, "puckfetcher")

        PC.Config()

        assert(os.path.isdir(directory) == True)
        config_file = os.path.join(directory, "config.yaml")
        assert(os.path.isfile(config_file) == True)

        contents = ""
        with open(config_file) as f:
            contents = f.read()

        assert(contents == "# Created by puckfetcher")

    def test_creates_empty_config_file(self):
        """
        Constructing a config with a directory provided, but with no config file provided, should
        create the file.
        """

        directory = os.path.join(TestConfig.xdg_config_home, "puckfetcher")

        PC.Config(config_dir=directory)

        assert(os.path.isdir(directory) == True)
        config_file = os.path.join(directory, "config.yaml")
        assert(os.path.isfile(config_file) == True)

        contents = ""
        with open(config_file) as f:
            contents = f.read()

        assert(contents == "# Created by puckfetcher")

    def test_save_cache_works(self):
        """Subscriptions should be saved correctly."""

        config_dir = os.path.join(TestConfig.xdg_config_home, "puckfetcher")
        cache_dir = os.path.join(TestConfig.xdg_cache_home, "puckfetcher")
        cache_file = os.path.join(cache_dir, "puckcache")

        config = PC.Config(config_dir=config_dir, cache_dir=cache_dir)

        sub = PS.Subscription(name="test", url="foo")

        config.subscriptions = [sub]

        config.save_cache()

        with open(cache_file, "rb") as f:
            bytestring = f.read()

            unpacked = msgpack.unpackb(bytestring, object_hook=PS.decode_subscription)
            unpacked_sub = unpacked[0]

            assert(unpacked_sub._provided_url == sub._provided_url)
            assert(unpacked_sub.name == sub.name)

    def test_load_state_works(self):
        """Subscriptions should be loaded correctly."""

        config_dir = os.path.join(TestConfig.xdg_config_home, "puckfetcher")
        cache_dir = os.path.join(TestConfig.xdg_cache_home, "puckfetcher")
        cache_file = os.path.join(cache_dir, "puckcache")

        subs = [PS.Subscription(name="test", url="foo")]

        with open(cache_file, "wb") as f:
            packed = msgpack.packb(subs, default=PS.encode_subscription)
            f.write(packed)

        config = PC.Config(config_dir=config_dir, cache_dir=cache_dir)

        config.load_state()

        sub = subs[0]

        assert(config.subscriptions[0].name == sub.name)
        assert(config.subscriptions[0]._provided_url == sub._provided_url)
