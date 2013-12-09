__author__ = 'Nathan Everitt'

from ..carriers import ups
from .. import data
from suds import WebFault
from pprint import pprint
from datetime import datetime

import test_credentials


import unittest
from base import TestCarrier

"""###
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('suds.transport').setLevel(logging.DEBUG)
###"""


class TestUPS(TestCarrier, unittest.TestCase):
    def init_carrier(self):
        return ups.UPSAPI(
            test_credentials.username,
            test_credentials.password,
            test_credentials.access_license_number,
            test_credentials.shipper_number,
            test_credentials.shipper_address
        )

if __name__ == '__main__':
    unittest.main()


"""###
try:
    request = data.Request(
        None,
        data.Address(
            contact_name='John Doe',
            phone_number='1234567890',
            street_lines=[
                '123 Main St',
                'Apt 666'
            ],
            city='Houston',
            subdivision='TX',
            postal_code='77047-1234',
            country='US',
            residential=True
        ),
        [
            data.Package(3, 4, 5, 6),
            data.Package(5, 6, 7, 8),
            data.Package(4, 5, 6, 7)
        ],
        ship_datetime=datetime(2013, 12, 16, 9, 30)
    )



    api = ups.UPSAPI(
        test_credentials.username,
        test_credentials.password,
        test_credentials.access_license_number,
        test_credentials.shipper_number,
        data.Address(
            contact_name='US Global Mail',
            phone_number='1234567890',
            street_lines=['1321 Upland Drive'],
            city='Houston',
            subdivision='TX',
            postal_code='77043',
            country='US'
        )
    )

    services = api.get_services(request)
    pprint(services)
    print services.keys()[0]
    print services.keys()[0].service_id

    #print api.delivery_datetime(services.keys()[0], request)
    #print api.quote(services.keys()[0], request)
    #request.destination = api.validate_address(request.destination)[1]
    #print request.destination

    shipment = api.ship(services.keys()[0], request)

    for i in range(len(request.packages)):
        with open('label-' + str(i) + '.pdf', 'w') as f:
            f.write(shipment.package_details[request.packages[i]]['label'])


    print services.keys()[0]
    print services.keys()[0].service_id

    print api.delivery_datetime(services.keys()[0], request)
    print api.quote(services.keys()[0], request)

except WebFault as err:
    print
    print '***** FAULT *****'
    print err.fault
    print err.message

###"""
