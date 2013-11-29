__author__ = 'Nathan Everitt'

#import logging
#logging.basicConfig(level=logging.DEBUG)
#logging.getLogger('suds.transit').setLevel(logging.DEBUG)

from ..carriers import ups
from .. import data
from suds import WebFault
from pprint import pprint

try:
    pak = data.Package(
        length=3, width=4, height=5, weight=6, imperial=True,
        origin=None,
        destination=data.Address(
            contact_name='Jonh Doe',
            phone_number='1234567890',
            street_lines=[
                '123 Main St',
                'Apt 666'
            ],
            city='Houston',
            subdivision='TX',
            postal_code='77047',
            country='US',
            residential=True
        )
    )

    services = ups.UPSAPI().get_services(pak)
    pprint(services)

    print ups.UPSAPI().delivery_datetime(services.keys()[0], pak)
except WebFault as err:
    print
    print '***** FAULT *****'
    print err.fault
    print err.message

#ups.ship()
