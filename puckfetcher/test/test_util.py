import shutil
import os
import tempfile

import puckfetcher.util as U


class TestUtil:
    @classmethod
    def setup_class(cls):
        cls.xdg_config_home = tempfile.mkdtemp()
        cls.old_xdg_config_home = os.environ.get("XDG_CONFIG_HOME", "")
        os.environ["XDG_CONFIG_HOME"] = cls.xdg_config_home

        cls.xdg_cache_home = tempfile.mkdtemp()
        cls.old_xdg_cache_home = os.environ.get("XDG_CACHE_HOME", "")
        os.environ["XDG_CACHE_HOME"] = cls.xdg_cache_home

        cls.xdg_data_home = tempfile.mkdtemp()
        cls.old_xdg_data_home = os.environ.get("XDG_DATA_HOME", "")
        os.environ["XDG_DATA_HOME"] = cls.xdg_data_home

    @classmethod
    def teardown_class(cls):
        os.environ["XDG_CONFIG_HOME"] = cls.old_xdg_config_home
        os.environ["XDG_CACHE_HOME"] = cls.old_xdg_cache_home
        os.environ["XDG_DATA_HOME"] = cls.old_xdg_data_home

        if os.path.exists(cls.xdg_config_home):
            shutil.rmtree(cls.xdg_config_home)

        if os.path.exists(cls.xdg_cache_home):
            shutil.rmtree(cls.xdg_cache_home)

        if os.path.exists(cls.xdg_data_home):
            shutil.rmtree(cls.xdg_data_home)

    def test_xdg_config_home_file_path_created(self):
        """Test that correct XDG_CONFIG_HOME is used and file is created."""

        expected = os.path.join(TestUtil.xdg_config_home, "foo", "bar", "baz")
        result = U.get_xdg_config_file_path("foo", "bar", "baz")

        assert(os.path.isfile(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_config_home):
            shutil.rmtree(TestUtil.xdg_config_home)
            assert(os.path.isfile(expected) == False)

    def test_xdg_config_home_dir_path_created(self):
        """Test that correct XDG_CONFIG_HOME is used and dir is created."""

        expected = os.path.join(TestUtil.xdg_config_home, "foo", "bar", "baz")
        result = U.get_xdg_config_dir_path("foo", "bar", "baz")

        assert(os.path.isdir(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_config_home):
            shutil.rmtree(TestUtil.xdg_config_home)
            assert(os.path.isdir(expected) == False)

    def test_xdg_cache_home_file_path_created(self):
        """Test that correct XDG_CACHE_HOME is used and file is created."""

        expected = os.path.join(TestUtil.xdg_cache_home, "foo", "bar", "baz")
        result = U.get_xdg_cache_file_path("foo", "bar", "baz")

        assert(os.path.isfile(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_cache_home):
            shutil.rmtree(TestUtil.xdg_cache_home)
            assert(os.path.isdir(expected) == False)

    def test_xdg_cache_home_dir_path_created(self):
        """Test that correct XDG_CACHE_HOME is used and dir is created."""

        expected = os.path.join(TestUtil.xdg_cache_home, "foo", "bar", "baz")
        result = U.get_xdg_cache_dir_path("foo", "bar", "baz")

        assert(os.path.isdir(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_cache_home):
            shutil.rmtree(TestUtil.xdg_cache_home)
            assert(os.path.isdir(expected) == False)

    def test_xdg_data_home_file_path_created(self):
        """Test that correct XDG_DATA_HOME is used and file is created."""

        expected = os.path.join(TestUtil.xdg_data_home, "foo", "bar", "baz")
        result = U.get_xdg_data_file_path("foo", "bar", "baz")

        assert(os.path.isfile(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_data_home):
            shutil.rmtree(TestUtil.xdg_data_home)
            assert(os.path.isdir(expected) == False)

    def test_xdg_data_home_dir_path_created(self):
        """Test that correct XDG_CONFIG_HOME is used and dir is created."""

        expected = os.path.join(TestUtil.xdg_data_home, "foo", "bar", "baz")
        result = U.get_xdg_data_dir_path("foo", "bar", "baz")

        assert(os.path.isdir(expected) == True)
        assert(expected == result)

        if os.path.exists(TestUtil.xdg_data_home):
            shutil.rmtree(TestUtil.xdg_data_home)
            assert(os.path.isdir(expected) == False)
