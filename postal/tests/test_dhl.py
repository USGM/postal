import unittest

from base import _AbstractTestCarrier
from ..carriers.dhl import DHLApi


class TestDHL(_AbstractTestCarrier, unittest.TestCase):
    carrier_class = DHLApi

    def test_international_delayed_shipment(self):
        raise unittest.SkipTest("Test server doesn't calculate offsets.")
