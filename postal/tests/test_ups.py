from unittest import SkipTest
import unittest
from money.Money import Money

from ..carriers.ups import UPSApi
from base import _AbstractTestCarrier
from ..data import Request, Address, Package, Declaration
from ..carriers.base import Carrier


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
