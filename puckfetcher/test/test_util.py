"""Tests for the util module."""
import timeit

import requests

import puckfetcher.util as util

TEST_URL = "https://raw.githubusercontent.com/andrewmichaud/puckfetcher/master/LICENSE"


def test_parse_int_string() -> None:
    """Test int string parser."""
    doc_example = "1 23 4-8 32 1"
    res = util.parse_int_string(doc_example)
    assert sorted(res) == [1, 4, 5, 6, 7, 8, 23, 32]

    invalid_nums = "1 fish a 4 1 23-- 5 5 5 5 5 9"
    res = util.parse_int_string(invalid_nums)
    assert sorted(res) == [1, 4, 5, 9]

    ranges = "1-5, 7-10, 9-12"
    res = util.parse_int_string(ranges)
    assert sorted(res) == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12]


def test_rate_limiting() -> None:
    """Test rate limiting (with a short limit, to not make tests drag on)."""

    @util.rate_limited(3600, "test")
    def _test_helper() -> None:
        requests.get(TEST_URL)

    _test_helper()

    res = timeit.timeit(_test_helper, number=4)
    assert abs(res - 4) < 1.0
