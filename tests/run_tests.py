import unittest

#import logging
#logging.basicConfig(level=logging.INFO)
#logging.getLogger('suds.transport').setLevel(logging.DEBUG)



if __name__ == '__main__':
    from test_fedex import TestFedEx
    from test_ups import TestUPS
    from test_dhl import TestDHL
    unittest.main()