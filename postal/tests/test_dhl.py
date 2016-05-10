import unittest

from ddt import ddt, data

from base import _AbstractTestCarrier
from ..carriers.dhl import DHLApi


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
