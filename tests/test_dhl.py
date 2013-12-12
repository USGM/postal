import unittest
from base import TestCarrier
from ..carriers.dhl import DHLApi


class TestDHL(TestCarrier, unittest.TestCase):
    carrier_class = DHLApi

if __name__ == '__main__':
    unittest.main()