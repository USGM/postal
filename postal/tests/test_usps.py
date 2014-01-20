import unittest
from unittest import SkipTest
from money import Money
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

    def test_refill(self):
        self.carrier.refill(Money('50.00', 'USD'))

    def test_repass(self):
        passphrase = 'asdfv87b34yubw3rg'
        self.carrier.change_passphrase('asdfv87b34yubw3rg')
        self.assertEqual(self.carrier.passphrase, passphrase)

if __name__ == '__main__':
    unittest.main()