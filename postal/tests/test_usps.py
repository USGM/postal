# coding=utf-8
import unittest
from unittest import SkipTest

from money import Money
from base import _AbstractTestCarrier, domestic, international
from ..carriers.usps import USPSApi
from postal import Address
from postal.carriers import Carrier


class TestUSPS(_AbstractTestCarrier, unittest.TestCase):
    carrier_class = USPSApi

    def test_international_delayed_shipment(self):
        raise SkipTest(
            "USPS does not support delayed international shipments.")

    def test_domestic_residential_shipment(self):
        raise SkipTest(
            "USPS does not charge extra for domestic shipments.")

    def test_refill(self):
        self.carrier.refill(Money('50.00', 'USD'))

    # Actually change3s the password now, so can't test this very easily.
    # def test_repass(self):
    #     passphrase = 'asdfv87b34yubw3rg'
    #     self.carrier.change_passphrase('asdfv87b34yubw3rg')
    #     self.assertEqual(self.carrier.passphrase, passphrase)

    def insurance(self):
        raise SkipTest("Insurance can't be checked on the test server.")

    def softpack(self):
        self.request.packages[0].package_type = Carrier.GENERIC_SOFTPAK
        services = self.carrier.get_services(self.request)
        sdict = services.keys()[0].ship(self.request)
        self.shipment_dict_check(sdict)

    @unittest.skip("""FIXME: Fails with: UnicodeEncodeError: 'ascii' codec can't encode character u'\xfc' in position 1: ordinal not in range(128)""")
    def test_number_subdivision(self):
        destination = Address(contact_name='Someone',
                              street_lines=['6 Someplace'],
                              city=u'Nüziders',
                              phone_number='5555555555888884444333',
                              subdivision='8',
                              postal_code='6714',
                              country='AU')
        self.international_request.destination = destination
        result = self.carrier.get_services(self.international_request)
        self.assertTrue(result)

    test_domestic_softpack = domestic(softpack)
    # FIXME: CarrierError: There is not enough money in the account to produce the indicium. Error encountered (Log ID: 40750)
    # test_international_softpack = international(softpack)
    test_domestic_insurance = domestic(insurance)
    
    # FIXME: AssertionError: USD 98.35 not less than USD 98.35
    # test_international_insurance = international(insurance)

    def test_international_insurance(self):
        raise SkipTest("""FIXME: Fails with: AssertionError: USD 81.32 not less than USD 81.32""")

    def test_no_etds(self):
        raise SkipTest("""Won't work with test account""")

    def test_international_rate_ship_match(self):
        raise SkipTest("""Won't work with test account""")
    
    def test_international_rate_ship_match_multiship(self):
        raise SkipTest("""Won't work with test account""")
    
    def test_international_multiship(self):
        raise SkipTest("""FIXME: Fails with: PdfReadError: Cannot read an empty file""")
