import unittest
from base import TestCarrier
from ..carriers.fedex import FedExApi


class TestFedEx(TestCarrier, unittest.TestCase):
    carrier_class = FedExApi

if __name__ == '__main__':
    unittest.main()