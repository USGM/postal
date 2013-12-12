import unittest

from test_fedex import TestFedEx
from test_ups import TestUPS
from test_dhl import TestDHL

#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)


def run():
    unittest.main()

if __name__ == '__main__':
    run()