__author__ = 'Nathan Everitt'

"""###
import logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('pycountry').setLevel(logging.CRITICAL)
logging.getLogger('suds.resolver').setLevel(logging.CRITICAL)
logging.getLogger('suds.xsd').setLevel(logging.CRITICAL)
logging.getLogger('suds.transit').setLevel(logging.DEBUG)
###"""

from ..carriers import ups
from .. import data
from suds import WebFault
from pprint import pprint

import test_credentials

try:
    pak = data.Package(
        length=3, width=4, height=5, weight=6, imperial=True,
        origin=None,
        destination=data.Address(
            contact_name='John Doe',
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

    api = ups.UPSAPI(
        test_credentials.username,
        test_credentials.password,
        test_credentials.access_license_number,
        test_credentials.shipper_number,
        data.Address(
            contact_name='US Global Mail',
            street_lines=['1321 Upland Drive'],
            city='Houston',
            subdivision='TX',
            postal_code='77043',
            country='US'
        )
    )

    #services = api.get_services(pak)
    #pprint(services)

    #print api.delivery_datetime(services.keys()[0], pak)
    #print api.quote(services.keys()[0], pak)

    """print api.validate_address(data.Address(
        contact_name='wat',
        street_lines=['shaserhse'],
        city='Houston',
        subdivision='TX',
        postal_code='77047',
        country='US'
    ))

    print api.validate_address(data.Address(
        contact_name='wat',
        street_lines=['Upland Dr'],
        city='Houston',
        subdivision='TX',
        postal_code='77047',
        country='US'
    ))"""

    print api.validate_address(data.Address(
        contact_name='wat',
        street_lines=['1321 Upl'],
        city='Houston',
        subdivision='TX',
        postal_code='77047',
        postal_code_extension='1234',
        country='US'
    ))

    """print api.validate_address(data.Address(
        street_lines=['27 Edison Furlong Rd'],
        city='Doylestown',
        subdivision='PA',
        postal_code='18901',
        country='US'
    ))"""

except WebFault as err:
    print
    print '***** FAULT *****'
    print err.fault
    print err.message

#ups.ship()