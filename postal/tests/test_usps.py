import unittest
from base import TestCarrier
from ..carriers.usps import USPSApi
from test_credentials import usps_credentials
#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)


class TestUSPS(TestCarrier, unittest.TestCase):
    def init_carrier(self):
        return USPSApi(**usps_credentials)

if __name__ == '__main__':
    unittest.main()