from ..carriers.ups import UPSApi

import unittest

from base import TestCarrier

"""###
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('suds.transport').setLevel(logging.DEBUG)
###"""

class TestUPS(TestCarrier, unittest.TestCase):
    carrier_class = UPSApi

if __name__ == '__main__':
    unittest.main()