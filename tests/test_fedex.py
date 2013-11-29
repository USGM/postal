import unittest
from base import TestCarrier
from ..carriers.fedex import FedExApi
from test_credentials import fedex_credentials
#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)


class TestFedEx(TestCarrier, unittest.TestCase):
    def init_carrier(self):
        return FedExApi(**fedex_credentials)

if __name__ == '__main__':
    unittest.main()