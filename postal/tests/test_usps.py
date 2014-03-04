import unittest
from unittest import SkipTest
from money import Money
from base import TestCarrier, domestic, international
from ..carriers.usps import USPSApi
from postal.carriers import Carrier

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

    def insurance(self):
        raise SkipTest("Insurance can't be checked on the test server.")

    def softpack(self):
        self.request.packages[0].package_type = Carrier.GENERIC_SOFTPAK
        services = self.carrier.get_services(self.request)
        sdict = services.keys()[0].ship(self.request)
        self.shipment_dict_check(sdict)

    test_domestic_softpack = domestic(softpack)
    test_international_softpack = international(softpack)
    test_domestic_insurance = domestic(insurance)
    test_international_insurance = international(insurance)

if __name__ == '__main__':
    unittest.main()