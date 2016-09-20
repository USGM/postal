import datetime
import unittest

import mock
from money import Money

from postal.carriers.aramex import AramexApi
from postal.carriers.base import Service
from postal.data import PackageType
from postal.exceptions import AddressError
from postal.postal import Postal
from postal.configuration_base import base_postal_configuration

from ..data import (Address, Package, Request, Declaration)
from .base import test_european, test_to, test_from
from .test_configuration import config
from decimal import Decimal

TWOPLACES = Decimal('0.01')


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self


class TestAramex (unittest.TestCase):

    def setUp(self):
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.european_address = Address(**test_european)

        declarations = [
            Declaration('Snaps', Money('3.95', 'USD'), 'US', 1, insure=False),
            Declaration('SIM Card', Money(45, 'USD'), 'US', 1, insure=True)]
        self.domestic_package = Package(2, 3, 4, .3, declarations=declarations)
        self.documents = Package(
            9, 12, .1, .2,
            PackageType(None, 'package', 'Package'),
            documents_only=True
        )
        self.international_package = Package(3, 4, 5, 6)
        self.carrier = AramexApi(postal_configuration=config,
            **config['carrier_inits']['Aramex'])

        self.mock_response = mock.MagicMock(HasErrors=False, notifications=())
        self.mock_response.TotalAmount = mock.MagicMock(Value=34.5, CurrencyCode='USD')
        self.rate_request = self.carrier.rates_client.factory.create('RateCalculatorRequest')
        self.rate_request.ClientInfo = self.carrier.client_info

        self.mock_ship_response = mock.MagicMock(HasErrors=False, notifications=())
        self.mock_ship_response.Shipments.ProcessedShipment = mock.MagicMock(ID=30511433772, HasErrors=False)
        self.ship_request = self.carrier.ship_client.factory.create('ShipmentCreationRequest')

    def test_rates_domestic(self):
        with mock.patch('postal.carriers.aramex.AramexApi.rates_client', new_callable=mock.Mock) as mock_rates_client:
            mock_rates_client.service.CalculateRate.return_value = self.mock_response
            request = Request(self.test_from, self.test_to, [self.domestic_package])
            services = self.carrier.get_services(request)
            calls = mock_rates_client.service.CalculateRate.call_args
            args = calls[0]
            self.validate_arguments(args, request)
            self.validate_services(services)

    def test_rates_international(self):
        with mock.patch('postal.carriers.aramex.AramexApi.rates_client', new_callable=mock.Mock) as mock_rates_client:
            mock_rates_client.service = mock.MagicMock()
            mock_rates_client.service.CalculateRate.return_value = self.mock_response
            request = Request(self.test_from, self.european_address, [self.international_package])
            services = self.carrier.get_services(request)
            calls = mock_rates_client.service.CalculateRate.call_args
            args = calls[0]
            self.validate_arguments(args, request)
            self.validate_services(services)

    def test_serviced_country(self):
        with mock.patch('postal.carriers.aramex.AramexApi.rates_client', new_callable=mock.Mock) as mock_rates_client:
            mock_rates_client.service = mock.MagicMock()
            mock_rates_client.service.CalculateRate.return_value = self.mock_response
            request = Request(self.test_from, self.test_to, [self.international_package])
            self.postal = Postal(base_postal_configuration)
            self.assertNotIn(AramexApi.name, self.postal.request_carrier_options(request))

    def validate_arguments(self, args, request):
        auth = args[0]
        origin = args[2]
        dest = args[3]
        details = args[4]

        self.assertEqual(self.carrier.client_info.UserName, auth.UserName)
        self.assertEqual(self.carrier.client_info.Password, auth.Password)
        self.assertEqual(request.origin.city, origin.City)
        self.assertEqual(request.destination.city, dest.City)
        self.assertEqual(request.origin.postal_code, origin.PostCode)
        self.assertEqual(request.destination.postal_code, dest.PostCode)
        self.assertEqual(request.total_weight(), details.ActualWeight.Value)
        self.assertEqual('LB', details.ActualWeight.Unit)

    def validate_services(self, services):
        self.assertTrue(services)
        for service, info in services.items():
            self.assertTrue(isinstance(service, Service))
            self.assertIsInstance(info['price'], dict)
            self.assertIsInstance(info['price']['total'], Money)
            self.assertIsInstance(info['price']['base_price'], Money)
            self.assertIsInstance(info['price']['fees'], Money)
            self.assertEqual(info['price']['total'], (info['price']['base_price'] + info['price']['fees']))
            if info['delivery_datetime'] is not None:
                self.assertIsInstance(info['delivery_datetime'], datetime)

    @mock.patch('postal.carriers.aramex.AramexApi.ship_client', new_callable=mock.Mock)
    @mock.patch('postal.carriers.aramex.AramexApi.format_label')
    @mock.patch('postal.carriers.aramex.AramexApi.quote')
    def test_shipping_domestic(self, mock_quote, mock_format_label, mock_ship_client):
        mock_ship_client.service = mock.MagicMock()
        mock_ship_client.service.CreateShipments.return_value = self.mock_ship_response;
        request = Request(self.test_from, self.test_to, [self.domestic_package])
        service = self.carrier.get_service('OND').ship(request)
        calls = mock_ship_client.service.CreateShipments.call_args
        args = calls[0]
        self.validate_ship_arguments(args, request)
        self.validate_ship_service(service)
        shipments = args[2]
        self.assertEqual(shipments.Shipment.Details.ProductGroup,'DOM') # For domestic shipments - Product group should be DOM

    @mock.patch('postal.carriers.aramex.AramexApi.ship_client', new_callable=mock.Mock)
    @mock.patch('postal.carriers.aramex.AramexApi.format_label')
    @mock.patch('postal.carriers.aramex.AramexApi.quote')
    def test_shipping_international(self, mock_quote, mock_format_label, mock_ship_client):
        mock_ship_client.service = mock.MagicMock()
        mock_ship_client.service.CreateShipments.return_value = self.mock_ship_response;
        request = Request(self.test_from, self.european_address, [self.international_package])
        service = self.carrier.get_service('PDX').ship(request)
        calls = mock_ship_client.service.CreateShipments.call_args
        args = calls[0]
        self.validate_ship_arguments(args, request)
        self.validate_ship_service(service)
        shipments = args[2]
        self.assertEqual(shipments.Shipment.Details.ProductGroup,'EXP') # For international shipments - Product group should be DOM

    def validate_ship_arguments(self, args, request):
        auth = args[0]
        shipments = args[2]
        origin = shipments.Shipment.Shipper.PartyAddress
        dest = shipments.Shipment.Consignee.PartyAddress
        shipment_details = shipments.Shipment.Details

        self.assertEqual(self.carrier.client_info.UserName, auth.UserName)
        self.assertEqual(self.carrier.client_info.Password, auth.Password)
        self.assertEqual(request.origin.city, origin.City)
        self.assertEqual(request.destination.city, dest.City)
        self.assertEqual(request.origin.postal_code, origin.PostCode)
        self.assertEqual(request.destination.postal_code, dest.PostCode)
        self.assertEqual(request.total_weight(), shipment_details.ActualWeight.Value)
        self.assertEqual('LB', shipment_details.ActualWeight.Unit)

        # Check declarations are set or not
        for i, package in enumerate(shipment_details.Items):
            self.assertEqual(package.Quantity, request.packages[0].declarations[i].units)
            self.assertEqual(package.GoodsDescription, request.packages[0].declarations[i].description)
            self.assertEqual(package.CustomsValue.Value, request.packages[0].declarations[i].value.amount)
        self.assertEqual(shipment_details.NumberOfPieces, len(request.packages))

    def validate_ship_service(self, service):
        self.assertTrue(service['shipment'])
        self.assertTrue(service['packages'])
        self.assertTrue(service['price'])

    def test_error_translation(self):
        request = Request(self.test_from, self.european_address, [self.international_package])
        with mock.patch('postal.carriers.base.Carrier.service_call') as mock_service_call:
            mock_service_call.return_value = AttrDict({
                'Notifications': AttrDict({
                    'Notification': [
                        AttrDict({'Code': 'ERR52', 'Message': 'DestinationAddress - City name is invalid (Cape Town)'})]
                }),
                'HasErrors': True,
            })
            self.assertRaises(AddressError, self.carrier.quote, self.carrier.get_service('PPX'), request)

    def test_tracking(self):
        self.carrier.track('123456')
        raise AssertionError
