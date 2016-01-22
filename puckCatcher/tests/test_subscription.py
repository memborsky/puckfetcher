import nose
from nose.tools import *

import puckCatcher.subscription as SUB
import puckCatcher.puckError as PE

@raises(PE.MalformedFeedError)
def test_emptyUrlBozos():
    """An empty URL should throw a MalformedFeedError"""
    emptyURLSubscription = SUB.Subscription(url="")
    emptyURLSubscription.getLatestEntry()

def test_emptyDaysParsedCorrectly():
    """
       A subscription constructed with an empty days list should have an array
       of all false for its days list.
    """
    emptySubscription = SUB.Subscription()
    assert(emptySubscription.days == [False]*7)

def test_numberDaysParsedCorrectly():
    """
       A subscription initialized with day numbers should parse them correctly.
       Invalid days should be silently ignored.
    """
    numbersSubscription = SUB.Subscription(days=[1, 2, 42, 5, 7, 0, 0, 1, 2])
    assert(numbersSubscription.days == [True,
                                        True,
                                        False,
                                        False,
                                        True,
                                        False,
                                        True])

def test_stringDaysParsedCorrectly():
    """
       A subscription initialized with day strings should parse them correctly.
       Invalid strings should be silently ignored.
    """
    stringSubscription = SUB.Subscription(days=[ "Monday"
                                               , "Tuesday"
                                               , "Wed"
                                               , "Fish"
                                               , "Friiiiiiiiiiiday"
                                               , "Sunblargl"])
    assert(stringSubscription.days == [True,
                                       True,
                                       True,
                                       False,
                                       True,
                                       False,
                                       True])

def test_mixedDaysParsedCorrectly():
    """
       A mixture of string and int days should be parsed correctly.
       Invalid elements should be silently ignored.
    """
    mixedSubscription = SUB.Subscription(days=[ "Monday"
                                               , 2
                                               , "Wed"
                                               , "Fish"
                                               , 42
                                               , "Friiiiiiiiiiiday"
                                               , "Sunblargl"])
    assert(mixedSubscription.days == [True,
                                       True,
                                       True,
                                       False,
                                       True,
                                       False,
                                       True])
