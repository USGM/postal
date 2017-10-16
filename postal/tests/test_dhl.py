import unittest

from datetime import datetime
from ddt import ddt, data
from mock import Mock, patch

from base import _AbstractTestCarrier
from postal.tests.fixtures.dhl import tracking_response, tracking_response_not_found
from postal.carriers.dhl import DHLApi


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
        result = self.carrier.track('1670466965')
        self.assertIn('No Shipments Found for AWBNumber', result['description'])
        self.assertEqual(result['status_code'], '209')
        self.assertFalse(result['location'])
        self.assertFalse(result['delivered'])
        self.assertFalse(result['finalized'])
