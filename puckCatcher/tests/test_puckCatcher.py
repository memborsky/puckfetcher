import nose
from nose.tools import *

import puckCatcher.puckCatcher as PC
import puckCatcher.puckError as PE

@raises(PE.MalformedFeedError)
def test_emptyUrlBozos():
    """An empty URL should throw a MalformedFeedError"""
    PC.getLatestEntry("")
