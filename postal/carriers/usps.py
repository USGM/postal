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
from ..exceptions import NotSupportedError, CarrierError
from ..data import Shipment


class USPSApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    name = 'USPS'
    multiship = False
    def __init__(
            self, user_id, password, test_mode, postal_configuration=None):
        super(USPSApi, self).__init__(postal_configuration)
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
            raise NotSupportedError("USPS does not support multiship.")

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

    @staticmethod
    def ship_date(date_time):
        return date_time.strftime('%d-%b-%Y')

    def get_services(self, request):
        self.no_multiship(request)
        package = request.packages[0]

        origin = request.origin or self.postal_configuration['shipper_address']
        if origin.country.alpha2 != 'US':
            raise NotSupportedError("USPS only ships from the US.")
        if request.destination.country.alpha2 == 'US':
            template = load_template('usps', 'rates_domestic.xml')
            international = False
        else:
            template = load_template('usps', 'rates_international.xml')
            international = True
        commercial = self.get_param(request, 'commercial', True)
        if commercial:
            commercial = 'Y'
            gift = 'N'
        else:
            commercial = 'N'
            gift = 'Y'

        if package.get_total_insured_value():
            if international:
                insurance = '<ExtraServices><ExtraService>1' \
                            '</ExtraService></ExtraServices>'
            else:
                insurance = '<SpecialServices><SpecialService>1' \
                            '</SpecialService></SpecialServices>'
        else:
            insurance = ''

        pounds = int(floor(package.weight))
        ounces = int(ceil((package.weight - pounds) * 16))
        dims = sorted([package.width, package.height, package.length])
        if (dims[0] > 12) or international:
            size = "LARGE"
            container = '<Container>RECTANGULAR</Container>'
        else:
            size = "REGULAR"
            container = '<Container>VARIABLE</Container>'
        girth = (dims[0] + dims[1]) * 2
        target_date = request.ship_datetime or datetime.now()
        ship_date = self.ship_date(target_date)

        value = request.get_total_insured_value()
        if str(value.currency) != 'USD':
            raise CarrierError("Value of goods must be in USD.")
        country = request.destination.country.name
        escape_dict = {
            'height': int(ceil(package.height)),
            'width': int(ceil(package.width)),
            'length': int(ceil(package.length)),
            'pounds': pounds,
            'ounces': ounces,
            'size': size,
            'girth': girth,
            'user_id': self.user_id,
            'origin_zip': origin.postal_code,
            'destination_zip': request.destination.postal_code,
            'ship_date': ship_date,
            'commercial': commercial,
            'gift': gift,
            'value': value.amount,
            'country': country}
        non_escape_dict = {
            'insurance': insurance,
            'container': container}
        call = populate_template(
            template, escape_dict, non_escape_dict)

        if international:
            result = self.make_call(self.rate_url, 'IntlRateV2', call)
        else:
            result = self.make_call(self.rate_url, 'RateV4', call)
        print result


# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [USPSApi]