from unittest import SkipTest
import unittest
from money.Money import Money

from ..carriers.ups import UPSApi
from base import TestCarrier
from ..data import Request, Address, Package, Declaration
from ..carriers.base import Carrier
from postal.exceptions import NotSupportedError


class TestUPS(TestCarrier, unittest.TestCase):
    carrier_class = UPSApi

    def skipper(self):
        raise SkipTest("UPS's API does not consistently "
                       "report this info during tests.")

    test_international_rate_ship_match_multiship = skipper
    test_international_rate_ship_match = skipper
    test_domestic_rate_ship_match_multiship = skipper
    test_domestic_rate_ship_match = skipper

    def test_adult_signature(self):
        try:
            self.carrier.get_service('03').ship(Request(
                Address(**{
                    'street_lines': ['1321 Upland Drive'],
                    'contact_name': 'Jonathan Piacenti',
                    'city': 'Houston',
                    'postal_code': '77043',
                    'phone_number': '18665968965',
                    'subdivision': 'TX',
                    'country': 'US'
                }),
                Address(
                    contact_name='TEST',
                    phone_number='0000000000',
                    street_lines=['DO NOT SHIP'],
                    city='MCLEAN',
                    subdivision='VA',
                    postal_code='22102',
                    country='US',
                    residential=True
                ),
                [
                    Package(1, 1, 1, 1, Carrier.GENERIC_PACKAGE, carrier_conversion=False, declarations=[
                        Declaration('your faec', Money('1000', 'USD'), 'US', 1, insure=True),
                    ], documents_only=False)
                ],
                extra_params={'UPS': {'signature': 'Adult'}}
            ))
        except NotSupportedError as err:
            if err.code == '121211':  # invalid accessory option
                return
            else:
                raise

if __name__ == '__main__':
    unittest.main()