from datetime import datetime
import httplib
from mock import Mock, patch
from unittest import SkipTest
import unittest

from money import Money
from suds.transport.http import HttpTransport, Reply

from base import _AbstractTestCarrier, test_from, test_to
from ddt import data, ddt, unpack
from postal.carriers.base import Carrier
from postal.carriers.fedex import FedExApi
from postal.data import Request, Address, Package, Declaration, Shipment
from postal.tests.fixtures.fedex import (tracking_response, tracking_response_StateOrProvinceCode,
                                         tracking_response_duplicate_way_bill, tracking_response_unique_identifier)


@ddt
class TestFedEx(_AbstractTestCarrier, unittest.TestCase):
    carrier_class = FedExApi

    @unittest.skip("""FIXME: Fails with: CarrierError: Error#1000: Authentication Failed""")
    def test_arbitrary_shipment_000(self):
        # A more complex shipment for this service to test.
        package_type = self.carrier.get_package_type('FEDEX_BOX')
        declarations = [
            Declaration('SIM Card', Money(45, 'USD'), 'US', 1, insure=True),
            Declaration('ECM Control Module', Money(319, 'USD'), 'US', 1,
                        insure=True),
            Declaration('Book', Money('12.78', 'USD'), 'US', 1, insure=False),
            Declaration('Book', Money('5.39', 'USD'), 'US', 1, insure=False),
            Declaration('Snaps', Money('3.95', 'USD'), 'US', 1, insure=False)]

        package = Package(
            1, 1, 1, 5,
            package_type, declarations=declarations,
            carrier_conversion=False, documents_only=False)

        service = self.carrier.get_service('INTERNATIONAL_ECONOMY')

        test_to_special = Address(
            contact_name='TEST',
            phone_number='0000000000',
            street_lines=['DO NOT SHIP'],
            city='Merida',
            subdivision='Yuc',
            postal_code='97117',
            country='MX',  # Mexico
            residential=True)

        request = Request(Address(**test_from), test_to_special, [package])

        response = service.ship(request)

        self.assertIsInstance(response, dict)
        self.assertIn('shipment', response)
        self.assertIn('price', response)
        self.assertIn('packages', response)
        self.assertIsInstance(response['shipment'], Shipment)
        self.assertIsInstance(response['price'], dict)
        self.assertIsInstance(response['price']['total'], Money)
        self.assertIsInstance(response['price']['fees'], Money)
        self.assertIsInstance(response['price']['base_price'], Money)
        self.assertIsInstance(response['packages'], dict)
        self.assertEqual(len(response['packages']), 1)
        self.assertIn(package, response['packages'])

        package_data = response['packages'][package]
        self.assertIsInstance(package_data, dict)
        self.assertIn('tracking_number', package_data)
        self.assertIn('label', package_data)
        self.assertIsInstance(package_data['tracking_number'], str)
        self.assertIsInstance(package_data['label'], str)

    @unittest.skip("""FIXME: Fails with: UnicodeEncodeError: 'ascii' codec can't encode character u'\xe9' in position 26: ordinal not in range(128)""")
    def test_unicode_characters(self):
        package = Package(
            11, 15, 3, 4, Carrier.GENERIC_PACKAGE, carrier_conversion=False,
            declarations=[
                Declaration('book', Money(45, 'USD'), 'US', 1, insure=False)],
            documents_only=False)

        test_to_special = Address(
            contact_name=u'Commission construction Qu\xe9bec',
            phone_number='0000000000',
            street_lines=['DO NOT SHIP'],
            city='Montreal',
            subdivision='PQ',  # the other abbreviation is QC
            postal_code='H2M0A7',
            country='CA'  # Canada
        )

        request = Request(Address(**test_from), test_to_special, [package])

        self.carrier.get_services(request)

    def test_heavy_domestic_envelope(self):
        package_type = self.carrier.get_package_type('FEDEX_ENVELOPE')
        package = Package(1, 1, 1, 3, package_type=package_type)
        request = Request(Address(**test_from), Address(**test_to), [package])
        response = self.carrier.get_services(request)
        self.assertTrue(response)
        response.keys()[0].ship(request)

    def test_duties_account(self):
        params = self.international_request.extra_params
        params['fedex_duties_account'] = '510087968'
        params['duties_address'] = Address(**test_from)
        response = self.carrier.get_services(self.international_request)
        self.assertTrue(response)
        response.keys()[0].ship(self.international_request)

    @unittest.skip("""FIXME: Fails with: CarrierError: FedEx returned a nonsense price. """
                   """Please contact their customer service about tracking number 794646546030. Error: 7000 |""" 
                   """Unable to obtain courtesy rates.""")
    def test_signature_confirmation(self):
        params = self.domestic_request.extra_params
        params['signature_required'] = 'Adult'
        response = self.carrier.get_services(self.domestic_request)
        self.assertTrue(response)
        response.keys()[0].ship(self.domestic_request)
        
    @unittest.skip("""FIXME: Fails with: CarrierError: FedEx returned a nonsense price.""")
    @unpack
    @data(('NORMAL_TYPE', False), ('PAYOR_LIST_SHIPMENT', True), ('PAYOR_LIST_PACKAGE', True))
    def test_get_price_dict(self, list_type, retail):
        info = Mock()
        if retail:
            info.ActualRateType = 'Dummy'
        else:
            info.ActualRateType = list_type
        spec = ('RateType', 'TotalNetCharge', 'TotalBaseCharge', 'Currency')
        details = [
            Mock(RateType='Dummy', spec=[]),
            Mock(
                RateType=list_type,
                TotalNetCharge=Mock(Amount='3.00', Currency='USD'),
                TotalBaseCharge=Mock(Amount='2.00', Currency='USD'),
                spec=spec,
            ),
            Mock(
                RateType=list_type,
                TotalNetCharge=Mock(Amount='5.00', Currency='USD'),
                TotalBaseCharge=Mock(Amount='3.00', Currency='USD'),
                spec=spec,
            )
        ]
        price_dict = FedExApi.get_price_dict(info, details, retail=True)
        self.assertEqual(price_dict['fees'], Money('1.00', 'USD'))
        self.assertEqual(price_dict['base_price'], Money('2.00', 'USD'))
        self.assertEqual(price_dict['total'], Money('3.00', 'USD'))
        
    @unittest.skip("""FIXME: Fails with: CarrierError: FedEx returned a nonsense price.""")
    @unpack
    @data(('NORMAL_TYPE', False), ('PAYOR_LIST_SHIPMENT', True), ('PAYOR_LIST_PACKAGE', True))
    def test_get_price_dict_negative_fees(self, list_type, retail):
        info = Mock()
        if retail:
            info.ActualRateType = 'Dummy'
        else:
            info.ActualRateType = list_type
        spec = ('RateType', 'TotalNetCharge', 'TotalBaseCharge', 'Currency')
        details = [
            Mock(RateType='Dummy', spec=[]),
            Mock(
                RateType=list_type,
                TotalNetCharge=Mock(Amount='15.00', Currency='USD'),
                TotalBaseCharge=Mock(Amount='17.00', Currency='USD'),
                spec=spec,
            ),
            Mock(
                RateType=list_type,
                TotalNetCharge=Mock(Amount='5.00', Currency='USD'),
                TotalBaseCharge=Mock(Amount='3.00', Currency='USD'),
                spec=spec,
            )
        ]
        price_dict = FedExApi.get_price_dict(info, details, retail=True)
        self.assertEqual(price_dict['fees'], Money('0.00', 'USD'))
        self.assertEqual(price_dict['base_price'], Money('15.00', 'USD'))
        self.assertEqual(price_dict['total'], Money('15.00', 'USD'))

    @patch.object(HttpTransport, 'send')
    def test_tracking(self, mock_send):
        mock_send.return_value = Reply(httplib.OK, {}, tracking_response)
        result = self.carrier.track('785568835233')
        self.assertEqual(result['delivered'], True)
        self.assertEqual(result['location'].street_lines, [' '])
        self.assertEqual(result['location'].city, u'LAGOS')
        self.assertEqual(result['location'].subdivision, u'LA')
        self.assertEqual(result['description'], u'Delivered')
        self.assertEqual(result['finalized'], True)
        self.assertEqual(result['status_code'], u'DL')
        self.assertEqual(result['event_time'], datetime(2017, 2, 14, 0, 0))

    @patch.object(HttpTransport, 'send')
    def test_tracking_StateOrProvinceCode(self, mock_send):
        mock_send.return_value = Reply(httplib.OK, {}, tracking_response_StateOrProvinceCode)
        result = self.carrier.track('785968343776')
        self.assertEqual(result['location'].street_lines, [' '])
        self.assertEqual(result['location'].city, u'ACCRA')
        self.assertFalse(result['location'].subdivision)
        self.assertEqual(result['description'], u'Delivered')
        self.assertEqual(result['finalized'], True)

    @unittest.skip("""FIXME: Fails with: TypeError: 'NoneType' object has no attribute '__getitem__'""")
    def test_domestic_address_validation(self):
        pass
    
    @unittest.skip("""FIXME: Fails with: TypeError: 'NoneType' object has no attribute '__getitem__'""")
    def test_international_address_validation(self):
        pass
    
    def _auth_failed(self):
        # this may not mean bad credentials but disabled service, need investigation
        raise SkipTest("""FIXME: Fails with: CarrierError: Error#1000: Authentication Failed""")
    
    def _nonsence_price_fail(self):
        raise SkipTest("""FIXME: Fails with: CarrierError: FedEx returned a nonsense price.""")
    
    test_no_etds = _auth_failed
    test_international_ship_package = _auth_failed
    test_international_rate_ship_match_multiship = _auth_failed
    test_international_rate_ship_match = _auth_failed
    test_international_multiship = _auth_failed
    test_duties_account = _auth_failed
    
    @patch.object(HttpTransport, 'send')
    def test_tracking_duplicate_waybill_returns_info(self, mock_send):
        mock_send.side_effect = (Reply(httplib.OK, {}, tracking_response_duplicate_way_bill),
                                 Reply(httplib.OK, {}, tracking_response_unique_identifier))
        result = self.carrier.track('783796503059')
        self.assertIn("event_time", result.keys())
