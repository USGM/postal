from unittest import SkipTest
from ..carriers.ups import UPSApi

import unittest

from base import TestCarrier


class TestUPS(TestCarrier, unittest.TestCase):
    carrier_class = UPSApi

    def skipper(self):
        raise SkipTest("UPS's API does not consistently "
                       "report this info during tests.")

    test_international_rate_ship_match_multiship = skipper
    test_international_rate_ship_match = skipper
    test_domestic_rate_ship_match_multiship = skipper
    test_domestic_rate_ship_match = skipper

if __name__ == '__main__':
    unittest.main()