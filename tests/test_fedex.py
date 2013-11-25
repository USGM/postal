import unittest
from datetime import datetime
from dateutil.relativedelta import relativedelta
from money.Money import Money
from ..carriers.base import Service

from ..carriers.fedex import FedExApi
from ..data import Address, Package, Declaration
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

#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)


class TestFedEx(unittest.TestCase):

    def setUp(self):
        self.fedex = FedExApi(**fedex_credentials)
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.package = Package(2, 3, 4, 5, self.test_from, self.test_to)
        self.declarations = [
            Declaration('McGuffin', Money('500.00', 'USD'), 'US', 7),
            Declaration('Brains', Money('1000.00', 'USD'), 'US', 5)]

    def test_get_services(self):
        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))

        print "=" * 79
        print "GET SERVICES"
        for service in services:
            print service, service.get_delivery_date(), service.get_price(
                self.package)

    def test_delayed_shipment(self):
        self.package.ship_datetime = datetime.now() + relativedelta(days=10)
        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))

        print "=" * 79
        print "DELAYED SHIPMENT"
        for service in services:
            print service, service.get_delivery_date(), service.get_price(
                self.package)

    def test_residential_shipment(self):
        self.test_to.residential = True
        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))

        print "=" * 79
        print "RESIDENTIAL SHIPMENT"
        for service in services:
            print service, service.get_delivery_date(), service.get_price(
                self.package)

    def test_declarations(self):
        self.package.declarations = self.declarations
        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))

        print "=" * 79
        print "WITH DECLARATIONS, NO INSURANCE"
        for service in services:
            print service, service.get_delivery_date(), service.get_price(
                self.package)

    def test_insurance(self):
        self.package.declarations = self.declarations
        self.package.insure = True

        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))

        print "=" * 79
        print "WITH DECLARATIONS AND INSURANCE"
        for service in services:
            print service, service.get_delivery_date(), service.get_price(
                self.package)

if __name__ == '__main__':
    unittest.main()