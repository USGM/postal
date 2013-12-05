import sys
from StringIO import StringIO
from datetime import datetime
from dateutil.relativedelta import relativedelta

from PyPDF2 import PdfFileReader
from money.Money import Money

from ..carriers.base import Service

from ..data import Address, Package, Declaration, Shipment, Request

test_from = {
    'street_lines': ['1321 Upland Drive'],
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

test_two = {
    'street_lines': ['1730 Mustang Trail'],
    'contact_name': 'Some Guy',
    'city': 'Kingwood',
    'postal_code': '77339',
    'subdivision': 'TX',
    'country': 'US'}

test_european = {
    'street_lines': ['House of Commons'],
    'contact_name': 'Jim Bob',
    'city': 'London',
    'postal_code': 'SW1A 0PW',
    'phone_number': '02072193000',
    'country': 'GB'}


class TestCarrier(object):
    """
    Base test class that should be used for most carriers to make sure they
    have a consistent interface. Subclassing requires multiple inheritance here
    since we're using this as an abstract class. We do this because unittest
    will detect subclasses of TestCase and run them, but we don't want that
    to happen for this parent class.
    """
    def init_carrier(self):
        """
        Tests should define this method. It should set up the carrier object
        for the tests and return it.
        """

    def setUp(self):
        self.carrier = self.init_carrier()
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.european_address = Address(**test_european)
        self.package = Package(2, 3, 4, 5)
        self.package2 = Package(4, 6, 6, 4)
        self.request = Request(self.test_from, self.test_to, [self.package])
        self.declarations = [
            Declaration('McGuffin', Money('500.00', 'USD'), 'US', 7),
            Declaration('Brains', Money('1000.00', 'USD'), 'US', 5)]

    def test_get_services(self):
        sys.stderr.write('\nTest: Get Services ')
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service in services.keys():
            self.assertTrue(isinstance(service, Service))

    def test_delayed_shipment(self):
        sys.stderr.write('\nTest: Delayed Shipment ')
        self.request.ship_datetime = datetime.now() + relativedelta(days=10)
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service, values in services.items():
            if values['delivery_datetime']:
                self.assertGreater(
                    values['delivery_datetime'],
                    self.request.ship_datetime)

    def test_residential_shipment(self):
        sys.stderr.write('\nTest: Residential Shipment ')
        services = self.carrier.get_services(self.request)
        cache_save = self.carrier.cache
        self.carrier.cache = {}
        self.test_to.residential = True
        services_residential = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service in services.keys():
            self.assertTrue(isinstance(service, Service))
        self.assertTrue(services_residential)
        for service in services_residential.keys():
            self.assertTrue(isinstance(service, Service))

        # Some services will be available for residential, and others not.
        # Iterate through and find all the ones that are available between
        # both.
        commercial = {service for service in services.keys()}
        residential = {service for services in services_residential.keys()}
        composite_set = commercial.intersection(residential)

        residential = [
            service.price(self.request) for service in services_residential
            if service in composite_set]
        self.carrier.cache = cache_save
        commercial = [
            service.price(self.request) for service in services
            if service in composite_set]
        residential = sum(residential)
        commercial = sum(commercial)
        self.assertGreater(residential, commercial)

    def test_insurance(self):
        sys.stderr.write('\nTest: Insurance ')

        services = self.carrier.get_services(self.request)
        normal_total = sum(
            [service.price(self.request) for service in services])

        self.carrier.cache = {}

        self.package.declarations = self.declarations
        services = self.carrier.get_services(self.request)
        declarations_total = sum(
            [service.price(self.request) for service in services])

        self.carrier.cache = {}

        self.request.insure = True
        services = self.carrier.get_services(self.request)
        insured_total = sum(
            [service.price(self.request) for service in services])
        self.assertEqual(normal_total, declarations_total)
        self.assertGreater(insured_total, normal_total)

    def test_address_validation(self):
        sys.stderr.write('\nTest: Address Validation ')
        score, address = self.carrier.validate_address(self.test_to)
        try:
            self.assertIsNotNone(address)
            self.assertTrue(address.residential)
            self.assertEqual(
                map(lambda a: a.upper(), address.street_lines),
                ["6410 THREEFLOWER LN"]
            )
            self.assertEqual(address.city.upper(), "KINGWOOD")
            self.assertEqual(address.subdivision, "TX")
            self.assertEqual(address.country.alpha2, "US")
            self.assertEqual(address.postal_code, "77345-2514")
            self.assertEqual(address.phone_number, self.test_to.phone_number)
            self.assertEqual(address.contact_name, self.test_to.contact_name)
            self.assertIsNot(address, self.test_to)
        except:
            sys.stderr.write(
                '\nUnable to validate\n' + str(self.test_to) +
                '\nInstead evaluated to:\n' + str(address)
            )
            raise

    def test_address_validation_b(self):
        sys.stderr.write('\nTest: Address Validation B ')
        score, address = self.carrier.validate_address(Address(
            contact_name='asdf', phone_number='1234567890',
            street_lines=['217 Edison Furlong Rd'],
            city='Doylestown', subdivision='PA', postal_code='18901',
            country='US', residential=True
        ))
        try:
            self.assertIsNotNone(address)
            self.assertTrue(address.residential)
            self.assertEqual(
                map(lambda a: a.upper(), address.street_lines),
                ["217 EDISON FURLONG RD"]
            )
            self.assertEqual(address.city.upper(), "DOYLESTOWN")
            self.assertEqual(address.subdivision, "PA")
            self.assertEqual(address.country.alpha2, "US")
            self.assertEqual(address.postal_code, "18901")
        except:
            sys.stderr.write(
                '\nUnable to validate\n ...' +
                '\nInstead evaluated to:\n' + str(address)
            )
            raise

    def test_international_services(self):
        sys.stderr.write('\nTest: International Services ')
        self.package.destination = self.european_address
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)

    def test_ship_package(self):
        sys.stderr.write('\nTest: Ship Package ')
        services = self.carrier.get_services(self.request)
        shipment = services.keys()[0].ship(self.request)
        self.assertIsInstance(shipment, Shipment)
        self.assertTrue(shipment.tracking_number)
        label = shipment.package_details[self.package]['label']
        PdfFileReader(StringIO(label))

    def test_multiship(self):
        sys.stderr.write('\nTest: Multiship ')
        services = self.carrier.get_services(self.request)
        self.request.packages.append(self.package2)
        shipment = services.keys()[0].ship(self.request)