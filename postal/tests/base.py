from StringIO import StringIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
from test_configuration import config

from PyPDF2 import PdfFileReader
from money.Money import Money

from ..carriers.base import Service, Carrier

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
    'contact_name': 'Some Dude',
    'phone_number': '1234567890',
    'street_lines': ['217 Edison Furlong Rd'],
    'city': 'Doylestown',
    'subdivision': 'PA',
    'postal_code': '18901',
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


def domestic(func):
    def wrapped(self, *args, **kwargs):
        if self.carrier.domestic:
            self.package = self.domestic_package
            self.package2 = self.domestic_package2
            self.request = self.domestic_request
            return func(self, *args, **kwargs)
    return wrapped


def international(func):
    def wrapped(self, *args, **kwargs):
        if self.carrier.international:
            self.package = self.international_package
            self.package2 = self.international_package2
            self.request = self.international_request
            return func(self, *args, **kwargs)
    return wrapped


class TestCarrier(object):
    """
    Base test class that should be used for most carriers to make sure they
    have a consistent interface. Subclassing requires multiple inheritance here
    since we're using this as an abstract class. We do this because unittest
    will detect subclasses of TestCase and run them, but we don't want that
    to happen for this parent class.
    """

    # Replace this with the target carrier.

    carrier_class = Carrier

    def init_carrier(self):
        return self.carrier_class(
            postal_configuration=config,
            **config['carrier_inits'][self.carrier_class.name])

    def setUp(self):
        self.carrier = self.init_carrier()
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.european_address = Address(**test_european)
        self.domestic_package = Package(2, 3, 4, 5)
        self.domestic_package2 = Package(4, 6, 6, 4)
        self.documents = Package(9, 12, .1, .2, document=True)
        self.international_package = Package(3, 4, 5, 6)
        self.international_package2 = Package(4, 2, 5, 28)

        self.domestic_request = Request(
            self.test_from, self.test_to, [
                self.domestic_package, self.documents])
        self.international_request = Request(
            self.test_from, self.european_address,
            [self.international_package, self.documents])
        self.declarations = [
            Declaration('McGuffin', Money('50.00', 'USD'), 'US', 7),
            Declaration('Brains', Money('60.00', 'USD'), 'US', 5)]
        self.declarations2 = [
            Declaration('Emotional Baggage', Money('49.00', 'USD'), 'US', 5),
            Declaration('Dehydrated Water', Money('53.40', 'USD'), 'US', 10)]
        self.document_declaration = [
            Declaration('Divorce papers', Money('0.00', 'USD'), 'US', 1)]
        self.international_package.declarations = self.declarations
        self.international_package2.declarations = self.declarations2
        self.documents.declarations = self.document_declaration

    def test_get_all_services(self):
        services = list(self.carrier.get_all_services())
        self.assertGreater(len(services), 0)
        for service in services:
            self.assertIsInstance(service, Service)

    def services(self):
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service, info in services.items():
            self.assertTrue(isinstance(service, Service))
            self.assertIsInstance(info['price'], Money)
            if info['delivery_datetime'] is not None:
                self.assertIsInstance(info['delivery_datetime'], datetime)

    def services_multiship(self):
        if not self.carrier.multiship:
            return
        self.request.packages.append(self.package2)
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service in services.keys():
            self.assertTrue(isinstance(service, Service))

    def delayed_shipment(self):
        ship_datetime = datetime.now() + relativedelta(days=2)
        # Avoid issuing requests for Saturday or Sunday in case pickup is not
        # provided on those days for carriers. The risk is still run of
        # hitting a holiday, of course.
        # The weekday count starts on Monday at 0.
        if ship_datetime.weekday() in [5, 6]:
            ### roll back to Friday because USPS doesn't support rates for
            ### shipments not within the next 3 days
            ship_datetime += relativedelta(days=-1)
        self.request.ship_datetime = ship_datetime

        services = self.carrier.get_services(self.request)
        self.assertTrue(services)
        for service, values in services.items():
            if values['delivery_datetime']:
                self.assertGreater(
                    values['delivery_datetime'], self.request.ship_datetime)

    def residential_shipment(self):
        if not self.carrier.address_validation:
            return
        if self.carrier.auto_residential:
            return
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

    def insurance(self):
        normal_rates = self.carrier.get_services(self.request)

        self.package.declarations = self.declarations

        self.carrier.cache = {}
        declaration_rates = self.carrier.get_services(self.request)

        for pak in self.request.packages:
            for dec in pak.declarations:
                dec.insure = True

        self.carrier.cache = {}
        insurance_rates = self.carrier.get_services(self.request)

        for service, info in normal_rates.items():
            self.assertEqual(
                info['price'], declaration_rates[service]['price'])

            if service in insurance_rates:
                self.assertLess(
                    info['price'], insurance_rates[service]['price'])

    def address_validation(self):
        if not self.carrier.address_validation:
            return
        score, address = self.carrier.validate_address(self.test_to)
        self.assertIsNotNone(address)
        self.assertTrue(address.residential)
        self.assertEqual(
            [a.upper() for a in address.street_lines],
            ["217 EDISON FURLONG RD"])
        self.assertEqual(address.city.upper(), "DOYLESTOWN")
        self.assertEqual(address.subdivision, "PA")
        self.assertEqual(address.country.alpha2, "US")
        self.assertEqual(address.postal_code.split('-')[0], "18901")

    def international_services(self):
        self.package.destination = self.european_address
        services = self.carrier.get_services(self.request)
        self.assertTrue(services)

    def ship_package(self):
        services = self.carrier.get_services(self.request)
        shipment = services.keys()[0].ship(self.request)
        self.assertIsInstance(shipment, Shipment)
        self.assertTrue(shipment.tracking_number)
        label = shipment.package_details[self.package]['label']
        PdfFileReader(StringIO(label))

    def multiship(self):
        services = self.carrier.get_services(self.request)
        self.request.packages.append(self.package2)
        self.assertIsInstance(services.keys()[0].ship(self.request), Shipment)

    test_domestic_services = domestic(services)
    test_domestic_services_multiship = domestic(services_multiship)
    test_domestic_delayed_shipment = domestic(delayed_shipment)
    test_domestic_residential_shipment = domestic(residential_shipment)
    test_domestic_insurance = domestic(insurance)
    test_domestic_address_validation = domestic(address_validation)
    test_domestic_ship_package = domestic(ship_package)
    test_domestic_multiship = domestic(multiship)
    test_international_services = international(services)
    test_international_services_multiship = international(services_multiship)
    test_international_delayed_shipment = international(delayed_shipment)
    test_international_residential_shipment = international(delayed_shipment)
    test_international_insurance = international(insurance)
    test_international_address_validation = international(address_validation)
    test_international_ship_package = international(ship_package)
    test_international_multiship = international(multiship)
