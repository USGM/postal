import unittest
from unittest import SkipTest
from base import TestCarrier
from ..carriers.usps import USPSApi


class TestUSPS(TestCarrier, unittest.TestCase):
    carrier_class = USPSApi

    def test_international_delayed_shipment(self):
        raise SkipTest(
            "USPS does not support delayed international shipments.")

    def test_domestic_residential_shipment(self):
        raise SkipTest(
            "USPS does not charge extra for domestic shipments.")

if __name__ == '__main__':
    unittest.main()