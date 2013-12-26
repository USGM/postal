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

        #def remove_all(node, name):
        #    for sub in node:
        #        if sub.tag == name:
        #            node.remove(sub)
        #        else:
        #            remove_all(sub, name)
        #remove_all(root, 'Restrictions')
        #remove_all(root, 'Prohibitions')
        #remove_all(root, 'Observations')
        #remove_all(root, 'ExpressMail')
        #remove_all(root, 'AreasServed')
        #remove_all(root, 'AdditionalRestrictions')
        #remove_all(root, 'CustomsForms')
        #remove_all(root, 'GXGLocations')
        #remove_all(root, 'MaxDimensions')
        #remove_all(root, 'MaxWeight')
        #remove_all(root, 'SvcCommitments')
        #print tostring(root)

        if root.tag == 'Error':
            raise CarrierError('Error#' + str(root.find('Number').text) + ': ' + str(root.find('Description').text))
        return root

    @staticmethod
    def ship_date(date_time):
        return date_time.strftime('%d-%b-%Y')

    def get_services(self, request):
        _ensure_supported(request)

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

        if international:
            if package.get_total_insured_value():
                insurance = '<ExtraServices><ExtraService>1' \
                            '</ExtraService></ExtraServices>'
            else:
                insurance = ''

        else:
            ### Special Services prices and availability will not be returned
            ### when Service = "ALL" or "ONLINE"
            insurance = ''

            #insurance = '<SpecialServices><SpecialService>1' \
            #            '</SpecialService></SpecialServices>'

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
        non_escape_dict = {'insurance': insurance, 'container': container}
        call = populate_template(
            template, escape_dict, non_escape_dict)

        from xml.sax.saxutils import unescape

        result = {}
        if international:
            response = self.make_call(self.rate_url, 'IntlRateV2', call)
            for service_tag in response.find('Package').iterfind('Service'):
                service = Service(
                    self,
                    service_tag.get('ID'),
                    _service_code_to_description.get(service_tag.get('ID'), service_tag.get('ID') + '**' + unescape(unescape(service_tag.find('SvcDescription').text)))
                )

                result[service] = dict(
                    price=Money(service_tag.find(
                        'CommercialPostage'
                        if request.destination.residential else
                        'Postage'
                    ).text, 'USD'),
                    delivery_datetime=None
                )
        else:
            response = self.make_call(self.rate_url, 'RateV4', call)
            for service_tag in response.find('Package').iterfind('Postage'):
                service = Service(
                    self,
                    service_tag.get('CLASSID'),
                    _service_code_to_description.get(service_tag.get('CLASSID'), service_tag.get('CLASSID') + '##' + unescape(unescape(service_tag.find('MailService').text)))
                )

                delivery = service_tag.find('CommitmentDate')
                if delivery is not None:  # `not` operator is marked for change in a future version
                    delivery = delivery.text.split('-')
                    delivery = datetime(year=int(delivery[0]), month=int(delivery[1]), day=int(delivery[2]))

                result[service] = dict(
                    price=Money(service_tag.find('Rate').text, 'USD'),
                    delivery_datetime=delivery
                )

        from pprint import pprint
        pprint(result)
        return result


def _ensure_supported(request):
    for package in request.packages:
        if package.weight > 70:
            raise NotSupportedError(
                'USPS does not ship packages that weigh more than 70 pounds.')


_service_code_to_description = {
    '2': 'Priority Mail Express 2-Day - Hold For Pickup',
    '3': 'Priority Mail Express 2-Day',
    '27': 'Priority Mail Express 2-Day - Flat Rate Envelope Hold For Pickup',
    '55': 'Priority Mail Express 2-Day - Flat Rate Boxes',
    '56': 'Priority Mail Express 2-Day - Flat Rate Boxes Hold For Pickup',
    '13': 'Priority Mail Express 2-Day - Flat Rate Envelope',
    '42': 'Priority Mail 2-Day - Small Flat Rate Envelope',
    '4': 'Standard Post',
    '40': 'Priority Mail 2-Day Window - Flat Rate Envelope',
    '31': 'Priority Mail Express 2-Day - Legal Flat Rate Envelope Hold For Pickup',
    '63': 'Priority Mail Express 2-Day - Padded Flat Rate Envelope Hold For Pickup',
    '62': 'Priority Mail Express 2-Day - Padded Flat Rate Envelope',
    '22': 'Priority Mail 2-Day - Large Flat Rate Box',
    '17': 'Priority Mail 2-Day - Medium Flat Rate Box',
    '28': 'Priority Mail 2-Day - Small Flat Rate Box',
    '16': 'Priority Mail 2-Day - Flat Rate Envelope',
    '44': 'Priority Mail 2-Day - Legal Flat Rate Envelope',
    '29': 'Priority Mail 2-Day - Padded Flat Rate Envelope',
    '38': 'Priority Mail 2-Day - Gift Card Flat Rate Envelope',
    '30': 'Priority Mail 2-Day - Legal Flat Rate Envelope',
    '6': 'Media Mail',
    '7': 'Library Mail',
    '1': 'Priority Mail Express International',
    '26': 'Priority Mail Express International Flat Rate Boxes',
    '11': 'Priority Mail International Large Flat Rate Box',
    '9': 'Priority Mail International Medium Flat Rate Box',
    '12': 'GXG Envelopes'
}
