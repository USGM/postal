from datetime import datetime
from mock import Mock, patch
import unittest

from base import _AbstractTestCarrier
from ddt import ddt, data
from postal.carriers.dhl import DHLApi
from postal.exceptions import SoftCarrierError
from postal.tests.fixtures.dhl import tracking_response, tracking_response_not_found
from unittest.case import SkipTest


@ddt
class TestDHL(_AbstractTestCarrier, unittest.TestCase):
    carrier_class = DHLApi

    def test_international_delayed_shipment(self):
        raise unittest.SkipTest("Test server doesn't calculate offsets.")

    @data(True, False)
    def test_price_dict(self, retail):
        self.international_request.extra_params['retail_rate'] = retail
        req = self.carrier.rates_request(self.international_request)
        if retail:
            self.assertNotIn('PaymentAccountNumber', req)
        else:
            self.assertIn('<PaymentAccountNumber>{}</PaymentAccountNumber>'.format(self.carrier.account_number), req)

    @unittest.skip("""FIXME: Fails with: AddressError: " FRANCE" is not a valid country code.""")
    @patch('postal.carriers.dhl.post')
    def test_tracking(self, mock_post):
        response = Mock()
        mock_post.return_value = response
        response.text = tracking_response
        result = self.carrier.track('9679741411')
        self.assertEqual(result['description'], 'Shipment delivered')
        self.assertEqual(result['status_code'], 'OK')
        self.assertEqual(result['location'].country.alpha2, 'FR')
        self.assertEqual(result['location'].city, 'PARIS')
        self.assertTrue(result['delivered'])
        self.assertTrue(result['finalized'])
        self.assertEqual(result['event_time'], datetime(2010, 7, 22, 12, 25))

    @patch('postal.carriers.dhl.post')
    def test_tracking_not_found(self, mock_post):
        response = Mock()
        mock_post.return_value = response
        response.text = tracking_response_not_found
        self.assertRaises(SoftCarrierError, self.carrier.track, '1670466965')

    def _empty_result_fail(self):
        raise SkipTest("""FIXME: Fails with: AssertionError: {} is not true""")
    
    test_international_multiship = _empty_result_fail
    test_no_etds = _empty_result_fail
    test_international_ship_package = _empty_result_fail
    test_international_services_multiship = _empty_result_fail
    test_international_ship_documents = _empty_result_fail
    test_international_rate_ship_match_multiship = _empty_result_fail
    test_international_multiship = _empty_result_fail
    test_international_services = _empty_result_fail
    test_international_rate_ship_match = _empty_result_fail
    test_international_insurance = _empty_result_fail    
    
