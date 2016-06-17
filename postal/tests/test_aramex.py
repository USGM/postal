import datetime
import unittest

import mock
from money import Money
from postal.carriers.aramex import AramexApi
from postal.carriers.base import Service
from postal.data import PackageType

from ..data import (Address, Package, Request)
from .base import test_european, test_to, test_from
from .test_configuration import config


class TestAramex (unittest.TestCase):   
    
    def setUp(self):
        self.test_from = Address(**test_from)
        self.test_to = Address(**test_to)
        self.european_address = Address(**test_european)
        self.domestic_package = Package(2, 3, 4, .3)
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
        self.rate_request = self.carrier.rates_client.factory.create('RateCalculatorRequest');
        self.rate_request.ClientInfo = self.carrier.client_info

    def test_rates_domestic(self):
        with mock.patch('postal.carriers.aramex.AramexApi.rates_client', new_callable=mock.Mock) as mock_rates_client:
            mock_rates_client.service.CalculateRate.return_value = self.mock_response;
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
