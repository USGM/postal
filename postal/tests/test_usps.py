import unittest
from base import TestCarrier
from ..carriers.usps import USPSApi


class TestUSPS(TestCarrier, unittest.TestCase):
    carrier_class = USPSApi

if __name__ == '__main__':
    unittest.main()