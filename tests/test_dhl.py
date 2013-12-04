import unittest
from base import TestCarrier
from ..carriers.dhl import DHLApi
from test_credentials import dhl_credentials
#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)


class TestDHL(TestCarrier, unittest.TestCase):
    def init_carrier(self):
        return DHLApi(**dhl_credentials)

if __name__ == '__main__':
    unittest.main()