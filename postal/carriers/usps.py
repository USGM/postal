"""
This is the module for interfacing with the United States Postal Service web
API. Unfortunately, USPS does not provide a WSDL specification, and so we are
bereft of the ability to use a library like Suds to do a lot of the lifting
for us.

Like DHL, we don't bother doing anything especially elaborate with XML
construction and instead rely on template files.
"""
from base64 import b64decode
from datetime import datetime
from math import ceil, floor
from time import timezone
from xml.etree.ElementTree import fromstring, tostring

from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from dateutil.relativedelta import relativedelta
from money import Money
from requests import post, RequestException

from base import Carrier, Service
from ..carriers.templates.constructor import load_template, populate_template
from ..exceptions import ExceedsLimitsError, CarrierError
from ..data import Shipment


class USPSApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    def __init__(
            self, user_id, password, test_mode, postal_configuration=None):
        super(USPSApi, self).__init__(postal_configuration)
        self.username = user_id
        super(USPSApi, self).__init__()
        self.user_id = user_id
        self.password = password

        self.rate_url = 'http://production.shippingapis.com/ShippingAPI.dll'
        if test_mode:
            self.ship_url = 'https://secure.shippingapis.com/' \
                            'ShippingAPITest.dll'
        else:
            # TODO: Get the production URL from USPS.
            self.ship_url = ''

    @staticmethod
    def no_multiship(request):
        if len(request.packages) > 1:
            raise ExceedsLimitsError("USPS Does not support multiship.")

    def make_call(self, url, api, call):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = post(
                url, data={'API': api, 'XML': call}, headers=headers)
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)
        root = fromstring(response.text)
        print tostring(root)

    def get_services(self, request):
        self.no_multiship(request)
        package = request.packages[0]
        template = load_template('usps', 'rates.xml')
        pounds = int(floor(package.weight))
        ounces = int(ceil((package.weight - pounds) * 16))
        dims = sorted([package.width, package.height, package.length])
        if dims[0] > 12:
            size = "LARGE"
        else:
            size = "REGULAR"
        girth = (dims[0] + dims[1]) * 2
        escape_dict = {
            'height': int(ceil(package.height)),
            'width': int(ceil(package.width)),
            'length': int(ceil(package.length)),
            'pounds': pounds,
            'ounces': ounces,
            'size': size,
            'girth': girth,
            'user_id': self.user_id,
            'origin_zip': request.origin.postal_code,
            'destination_zip': request.destination.postal_code}
        call = populate_template(template, escape_dict)
        result = self.make_call(self.rate_url, 'RateV4', call)


# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [USPSApi]