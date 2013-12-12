__author__ = 'Nathan Everitt'

import unittest

from suds import WebFault
from pprint import pprint
from datetime import datetime
import money

from base import TestCarrier, Service
from ..carriers import ups
from .. import data
import test_credentials

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
            city='Round Rock',
            subdivision='TX',
            postal_code='78665',
            country='US',
            residential=True
        ),
        [
            #data.Package(3, 4, 5, 6, declarations=[data.Declaration('asdf', money.Money(101, 'USD'), 'US', 1)]),
            #data.Package(5, 6, 7, 8, declarations=[data.Declaration('qwer', money.Money(50, 'USD'), 'US', 2)]),
            #data.Package(4, 5, 6, 7, declarations=[data.Declaration('zxcv', money.Money(10, 'USD'), 'US', 3)])
            data.Package(23, 11, 11, 18, declarations=[data.Declaration('omg', money.Money(500, 'USD'), 'US', 1)]),
            data.Package(23, 11, 11, 14, declarations=[data.Declaration('omg', money.Money(500, 'USD'), 'US', 1)]),
            data.Package(24, 4, 3, 2, declarations=[data.Declaration('omg', money.Money(200, 'USD'), 'US', 1)])
        ],
        ship_datetime=datetime(2013, 12, 16, 9, 30),
        insure=True
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
    #print services.keys()[0]
    #print services.keys()[0].service_id

    #print api.delivery_datetime(services.keys()[0], request)
    #print api.quote(services.keys()[0], request)
    #request.destination = api.validate_address(request.destination)[1]
    #print request.destination

    #shipment = api.ship(services.keys()[0], request)
    #for i in range(len(request.packages)):
    #    with open('label-' + str(i) + '.pdf', 'w') as f:
    #        f.write(shipment.package_details[request.packages[i]]['label'])


    #print api.delivery_datetime(services.keys()[0], request)

    #print api.quote(services.keys()[0], request)

    #request.insure = True
    #print api.quote(services.keys()[0], request)

    #print api.quote(Service(api, '03', 'UPS Ground'), request)

    print api.ship(Service(api, '03', 'Ground'), request)

except WebFault as err:
    print
    print '***** FAULT *****'
    print err.fault
    print err.message

###"""
