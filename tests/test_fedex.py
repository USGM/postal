import unittest
from datetime import datetime
from dateutil.relativedelta import relativedelta
from money.Money import Money
from ..carriers.base import Service

from ..carriers.fedex import FedExApi
from ..data import Address, Package, Declaration
from test_credentials import fedex_credentials

test_from = {
    'street_lines': ['1321 Jimmy Upland Drive'],
    'contact_name': 'Jonathan Piacenti',
    'city': 'Houston',
    'postal_code': '77043',
    'phone_number': '18665968965',
    'subdivision': 'TX',
    'country': 'US'}

test_to = {
    'street_lines': ['6410 Three Flower Lane'],
    'contact_name': 'No one in particular',
    'city': 'Kingwood',
    'postal_code': '77345',
    'phone_number': '5555555555',
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

    def test_delayed_shipment(self):
        self.package.ship_datetime = datetime.now() + relativedelta(days=10)
        services = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            if service.delivery_date:
                self.assertGreater(
                    service.delivery_date, self.package.ship_datetime)

    def test_residential_shipment(self):
        services = self.fedex.get_services(self.package)
        cache_save = self.fedex.cache
        self.fedex.cache = {}
        self.test_to.residential = True
        services_residential = self.fedex.get_services(self.package)
        self.assertTrue(services)
        for service in services:
            self.assertTrue(isinstance(service, Service))
        self.assertTrue(services_residential)
        for service in services_residential:
            self.assertTrue(isinstance(service, Service))

        # Some services will be available for residential, and others not.
        # Iterate through and find all the ones that are available between
        # both.
        commercial = {service.service_id for service in services}
        residential = {service.service_id for service in services_residential}
        composite_set = commercial.intersection(residential)

        residential = [
            service.get_price(self.package) for service in services_residential
            if service.service_id in composite_set]
        self.fedex.cache = cache_save
        commercial = [
            service.get_price(self.package) for service in services
            if service.service_id in composite_set]
        residential = sum(residential)
        commercial = sum(commercial)
        self.assertGreater(residential, commercial)

    def test_insurance(self):

        services = self.fedex.get_services(self.package)
        normal_total = sum(
            [service.get_price(self.package) for service in services])

        self.fedex.cache = {}

        self.package.declarations = self.declarations
        services = self.fedex.get_services(self.package)
        declarations_total = sum(
            [service.get_price(self.package) for service in services])

        self.fedex.cache = {}

        self.package.insure = True
        services = self.fedex.get_services(self.package)
        insured_total = sum(
            [service.get_price(self.package) for service in services])
        self.assertEqual(normal_total, declarations_total)
        self.assertGreater(insured_total, normal_total)

    def test_address_validation(self):
        score, address = self.fedex.validate_address(self.test_to)
        self.assertTrue(address.residential)
        self.assertEqual(address.street_lines, ["6410 Threeflower Ln"])
        self.assertEqual(address.city, "Kingwood")
        self.assertEqual(address.subdivision, "TX")
        self.assertEqual(address.country.alpha2, "US")
        self.assertEqual(address.postal_code, "77345-2514")
        self.assertEqual(address.phone_number, self.test_to.phone_number)
        self.assertEqual(address.contact_name, self.test_to.contact_name)
        self.assertIsNot(address, self.test_to)

if __name__ == '__main__':
    unittest.main()