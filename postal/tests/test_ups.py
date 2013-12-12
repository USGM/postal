from ..carriers.ups import UPSApi

__author__ = 'Nathan Everitt'

import unittest

from base import TestCarrier


class TestUPS(TestCarrier, unittest.TestCase):
    carrier_class = UPSApi

if __name__ == '__main__':
    unittest.main()