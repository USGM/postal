from unittest import SkipTest
import unittest

from datetime import datetime
from ddt import data, ddt
from mock import Mock
from money.Money import Money

from ..carriers.ups import UPSApi
from base import _AbstractTestCarrier
from ..data import Request, Address, Package, Declaration
from ..carriers.base import Carrier


@ddt
class TestUPS(_AbstractTestCarrier, unittest.TestCase):
    carrier_class = UPSApi

    def skipper(self):
        raise SkipTest("UPS's API does not consistently "
                       "report this info during tests.")

    test_international_rate_ship_match_multiship = skipper
    test_international_rate_ship_match = skipper
    test_domestic_rate_ship_match_multiship = skipper
    test_domestic_rate_ship_match = skipper

    def test_adult_signature(self):
        from_address = Address(
                street_lines=['1321 Upland Drive'],
                contact_name='Jonathan Piacenti',
                city='Houston',
                postal_code='77043',
                phone_number='18665968965',
                subdivision='TX',
                country='US')
        to_address = Address(
                street_lines=['1730 Mustang Trail'],
                contact_name='Jonathan Piacenti',
                city='Kingwood',
                postal_code='77339',
                phone_number='18665968965',
                subdivision='TX',
                country='US')
        declaration = Declaration('Test Declaration',
                                  Money('1000', 'USD'), 'US', 1, insure=True)
        package = Package(1, 1, 1, 1, Carrier.GENERIC_PACKAGE, 
                          carrier_conversion=False,
                          declarations=[declaration],
                          documents_only=False)
        extra_params={'signature_required': 'Adult'}
        request = Request(from_address, to_address, packages=[package],
                          extra_params=extra_params)
        self.carrier.get_service('03').ship(request)

    @data(True, False)
    def test_get_price(self, retail):
        node = Mock(spec=('TotalCharges', 'NegotiatedRateCharges'))
        if retail:
            node.TotalCharges.MonetaryValue = '2.00'
            node.TotalCharges.CurrencyCode = 'USD'
        else:
            node.NegotiatedRateCharges = Mock(spec=('TotalCharge',))
            node.NegotiatedRateCharges.TotalCharge.MonetaryValue = '2.00'
            node.NegotiatedRateCharges.TotalCharge.CurrencyCode = 'USD'
        price_dict = self.carrier._get_price(node, retail=retail)
        self.assertEqual(price_dict['total'], Money('2.00', 'USD'))
        self.assertEqual(price_dict['fees'], Money('0.00', 'USD'))
        self.assertEqual(price_dict['base_price'], Money('2.00', 'USD'))

    def test_tracking(self):
        result = self.carrier.track('1Z12345E6205277936')
        self.assertEqual(result['delivered'], False)
        self.assertEqual(result['location'].street_lines, [' '])
        self.assertEqual(result['location'].city, u'ANYTOWN')
        self.assertEqual(result['location'].subdivision, u'GA')
        self.assertEqual(
            result['description'],
            u"THE RECEIVER'S LOCATION WAS CLOSED ON THE 2ND DELIVERY ATTEMPT. A 3RD DELIVERY ATTEMPT WILL BE MADE"
        )
        self.assertEqual(result['finalized'], False)
        self.assertEqual(result['status_code'], u'X')
        self.assertEqual(result['event_time'], datetime(2010, 8, 30, 10, 39, 0))

