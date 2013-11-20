import unittest

from ..carriers.fedex import FedExApi
from ..data import Address, Package
from test_credentials import fedex_credentials

test_from = {
    'street_lines': ['1321 Upland Drive Houston'],
    'contact_name': 'Jonathan Piacenti',
    'city': 'Houston',
    'postal_code': '77043',
    'phone_number': '18665968965',
    'subdivision': 'TX',
    'country': 'US'}

test_to = {
    'street_lines': ['14781 Memorial Dr.'],
    'contact_name': 'Memorial Postal',
    'city': 'Houston',
    'postal_code': '77079',
    'phone_number': '2814971446',
    'subdivision': 'TX',
    'country': 'US'}

import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('suds.transport').setLevel(logging.DEBUG)

class TestFedEx(unittest.TestCase):

    def setUp(self):
        self.fedex = FedExApi(**fedex_credentials)
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.package = Package(2, 3, 4, 5, self.test_from, self.test_to)

    def test_get_services(self):
        self.fedex.get_services(self.package)

if __name__ == '__main__':
    unittest.main()