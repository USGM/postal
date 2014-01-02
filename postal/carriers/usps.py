"""
This is the module for interfacing with the United States Postal Service web
API. Unfortunately, USPS does not provide a WSDL specification, and so we are
bereft of the ability to use a library like Suds to do a lot of the lifting
for us.

Like DHL, we don't bother doing anything especially elaborate with XML
construction and instead rely on template files.
"""
from base64 import b64decode
from datetime import datetime, date
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
from postal.carriers.templates.constructor import iter_populate_template
from xml.sax.saxutils import unescape
from postal.data import Request


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

    def make_call(self, url, api, call):
        print '>>>>', call

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = post(
                url, data={'API': api, 'XML': call}, headers=headers)
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)
        root = fromstring(response.text)

        #"""###
        def remove_all(node, name):
            for sub in node:
                if sub.tag == name:
                    node.remove(sub)
                else:
                    remove_all(sub, name)
        remove_all(root, 'Restrictions')
        remove_all(root, 'Prohibitions')
        remove_all(root, 'Observations')
        remove_all(root, 'ExpressMail')
        remove_all(root, 'AreasServed')
        remove_all(root, 'AdditionalRestrictions')
        remove_all(root, 'CustomsForms')
        remove_all(root, 'GXGLocations')
        remove_all(root, 'MaxDimensions')
        remove_all(root, 'MaxWeight')
        #remove_all(root, 'SvcCommitments')
        remove_all(root, 'Location')
        remove_all(root, 'CommitmentName')
        print '<<<<', tostring(root)
        ###"""

        if root.tag == 'Error':
            raise CarrierError('Error#' + str(root.find('Number').text) + ': ' + str(root.find('Description').text))
        return root

    @staticmethod
    def ship_date(date_time):
        return date_time.strftime('%d-%b-%Y')

    def get_all_services(self):
        return [
            Service(self, 'EXPRESS', 'Express'),
            Service(self, 'FIRST CLASS', 'First Class'),
            Service(self, 'PRIORITY', 'Priority'),
            Service(self, 'EXPRESS COMMERCIAL', 'Express Commercial'),
            Service(self, 'FIRST CLASS COMMERCIAL', 'First Class Commercial'),
            Service(self, 'PRIORITY COMMERCIAL', 'Priority Commercial')
        ]

    def get_services(self, request):
        self._ensure_supported(request)

        origin = request.origin or self.postal_configuration['shipper_address']

        if request.destination.country.alpha2 == 'US':
            return self._get_rates_domestic(request, origin)
        else:
            return self._get_rates_international(request, origin)

    def _get_rates_international(self, request, origin):
        if request.ship_datetime and \
                request.ship_datetime.date() != date.today():
            raise NotSupportedError(
                'USPS does not support delayed international shipments.')

        commercial = self.get_param(request, 'commercial', True)
        if commercial:
            commercial = 'Y'
            gift = 'N'
        else:
            commercial = 'N'
            gift = 'Y'

        size = 'LARGE'
        container = 'RECTANGULAR'

        escape_dict = {
            'user_id': self.user_id,
            'origin_zip': origin.postal_code,
            'destination_zip': request.destination.postal_code,
            'commercial': commercial,
            'gift': gift,
            'country': request.destination.country.name,
            'size': size,
            'container': container
        }

        package_escape, package_nonescape = _get_package_parameters(
            request.packages[0], 0, origin, request.destination)
        escape_dict.update(package_escape)

        escape_dict['value'] = request.get_total_insured_value().amount

        non_escape_dict = package_nonescape
        call = populate_template(load_template('usps', 'rates_international.xml'), escape_dict, non_escape_dict)
        response = self.make_call(self.rate_url, 'IntlRateV2', call)

        result = {}
        for service_tag in response.find('Package').iterfind('Service'):

            if request.get_total_insured_value() > 0:
                insurance_price = None

                for extra_service in service_tag.find('ExtraServices'):
                    if extra_service.find('ServiceID').text.strip() != '1':
                        ### 1 = insurance
                        continue

                    if extra_service.find('OnlineAvailable') \
                            .text.strip().lower() != 'true':
                        continue

                    insurance_price = Money(
                        extra_service.find('PriceOnline').text, 'USD'
                    ) * ceil(
                        request.get_total_insured_value().amount / 100
                    )

                if insurance_price is None:
                    continue  # this is not the service we're looking for

            else:
                insurance_price = Money(0, 'USD')

            service = Service(
                self,
                'I' + service_tag.get('ID'),
                _service_code_to_description.get(service_tag.get('ID'), service_tag.get('ID') + '**' + unescape(unescape(service_tag.find('SvcDescription').text)))
            )

            result[service] = dict(
                price=(Money(service_tag.find(
                    'CommercialPostage'
                    if request.destination.residential else
                    'Postage'
                ).text, 'USD') + insurance_price),
                delivery_datetime=None
            )

        return result

    def _get_rates_domestic(self, request, origin, services=None):
        if not services:
            req = request.shallow_copy()
            req.packages = []
            serv = []

            for pak in request.packages:
                req.packages += [pak, pak]
                serv += ['FIRST CLASS COMMERCIAL', 'PRIORITY COMMERCIAL']

            return self._get_rates_domestic(req, origin, serv)

        ship_date = self.ship_date(request.ship_datetime or datetime.now())

        escape_dict = {
            'user_id': self.user_id,
            'origin_zip': origin.postal_code,
            'destination_zip': request.destination.postal_code,
            'ship_date': ship_date,
            'value': request.get_total_insured_value().amount}
        non_escape_dict = {
            'packages': iter_populate_template(['usps', 'package_domestic.xml'], (
                _get_package_parameters(
                    package, index, origin, request.destination, ship_date,
                    services[index] if services else 'ALL'
                )
                for index, package in enumerate(request.packages)
            ))
        }
        call = populate_template(load_template('usps', 'rates_domestic.xml'), escape_dict, non_escape_dict)

        response = self.make_call(self.rate_url, 'RateV4', call)

        result = {}
        for package_tag in response.iterfind('Package'):
            ### assuming multiple responses to the same package being returned
            ### - a response to the recursive call in the first if-branch of
            ### this method
            for service_tag in package_tag.iterfind('Postage'):

                """###
                ### temporary early-outs to make creating the service tables easier
                if service_tag.find('MailService').text.find('Hold For Pickup') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Flat Rate Box') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Window') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Media Mail') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Library Mail') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Gift Card') >= 0:
                    continue
                if service_tag.find('MailService').text.find('Small Flat Rate Envelope') >= 0:
                    continue
                ###"""

                service_id = 'D' + service_tag.get('CLASSID')

                #if service_id not in _service_code_to_description:
                #    continue

                service = Service(
                    self,
                    service_id,
                    #_service_code_to_description[service_id]
                    _service_code_to_description.get(
                        service_id,
                        service_tag.get('CLASSID') + '##' + unescape(unescape(service_tag.find('MailService').text))
                    )
                )

                delivery = service_tag.find('CommitmentDate')
                if delivery is not None:  # `not` operator is marked for change in a future version
                    delivery = delivery.text.split('-')
                    delivery = datetime(
                        year=int(delivery[0]),
                        month=int(delivery[1]),
                        day=int(delivery[2]),
                        hour=23,
                        minute=59
                    )

                result[service] = dict(
                    price=Money(service_tag.find('Rate').text, 'USD'),
                    delivery_datetime=delivery
                )

                if not services and request.get_total_insured_value():
                    insurance_request = request.shallow_copy()
                    insurance_request.packages = []
                    insurance_services = []

                    ### TODO: find a more robust solution than clipping the list
                    #if len(list(result.items())) > 25:
                    #   raise Exception()

                    for service, info in list(result.items())[:25]:  # limited to 25 packages
                        ### not supporting external queries of more than one package
                        insurance_request.packages.append(request.packages[0])
                        insurance_services.append(_service_code_to_other_service_code[service.service_id])

                        # Service must be Priority Express, Priority Express SH, Priority Express Commercial, Priority Express SH Commercial, First Class, Priority, Priority Commercial,
                        # Standard Post, Library, BPM, Media, ALL, or ONLINE

                    print self._get_rates_domestic(insurance_request, origin, insurance_services)#service.service_id)

                        #result[service][price] +=



        #from pprint import pprint
        #pprint(result)
        return result

    def quote(self, service, request):
        try:
            return self.get_services(request)[service]['price']
        except KeyError:
            raise NotSupportedError(
                'USPS has no rates for that service and request.')

    def _ensure_supported(self, request):
        origin = request.origin or self.postal_configuration['shipper_address']
        if origin.country.alpha2 != 'US':
            raise NotSupportedError("USPS only ships from the US.")

        if len(request.packages) > 1:
            raise NotSupportedError("USPS does not support multiship.")

        for package in request.packages:
            if package.weight > 70:
                raise NotSupportedError(
                    'USPS does not ship packages that weigh more '
                    'than 70 pounds.')

        if str(request.get_total_insured_value().currency) != 'USD':
            raise NotSupportedError("Value of goods must be in USD.")


def _get_package_parameters(package, index, origin, destination, ship_date=None, service='ALL'):
    """
    returns: (escape:{...}, nonescape:{...})
    """
    international = (origin.country != destination.country)
    if international:
        if package.get_total_insured_value() > 0:
            ### can't treat Money as boolean

            insurance = \
                '<ExtraServices><ExtraService>1</ExtraService></ExtraServices>'
        else:
            insurance = ''
    else:
        ### Special Services prices and availability will not be returned
        ### when Service = "ALL" or "ONLINE"
        insurance = ''

        #insurance = '<SpecialServices><SpecialService>1' \
        #            '</SpecialService></SpecialServices>'

    length, width, height = sorted([package.width, package.height, package.length])
    if length > 12 or international:
        size = 'LARGE'
        container = 'RECTANGULAR'
    else:
        size = 'REGULAR'
        container = 'VARIABLE'

    girth = (width + height) * 2

    pounds = int(floor(package.weight))
    ounces = int(ceil((package.weight - pounds) * 16))

    return (
        dict(
            service=service,
            origin_zip=origin.postal_code,
            destination_zip=destination.postal_code,
            length=length,
            width=width,
            height=height,
            pounds=pounds,
            ounces=ounces,
            id=index,
            size=size,
            container=container,
            girth=girth,
            value=(
                package.get_total_declared_value().amount
                if international else
                package.get_total_insured_value().amount
            ),
            ship_date=ship_date
        ),
        dict(insurance=insurance)
    )

_service_code_to_description = {
    'D1': 'Priority Mail 2-Day',
    'D16': 'Priority Mail 2-Day - Flat Rate Envelope',
    'D44': 'Priority Mail 2-Day - Legal Flat Rate Envelope',
    'D29': 'Priority Mail 2-Day - Padded Flat Rate Envelope',

    #'D4': 'Standard Post',
    #'D3': 'Priority Mail Express 2-Day',
    #'D13': 'Priority Mail Express 2-Day - Flat Rate Envelope',
    #'D30': 'Priority Mail Express 2-Day - Legal Flat Rate Envelope',
    #'D62': 'Priority Mail Express 2-Day - Padded Flat Rate Envelope',
}

_service_code_to_other_service_code = {
    'D1': 'PRIORITY COMMERCIAL',
    'D16': 'PRIORITY COMMERCIAL',
    'D44': 'PRIORITY COMMERCIAL',
    'D29': 'PRIORITY COMMERCIAL',
    '?': 'FIRST CLASS COMMERCIAL',
    '??': 'EXPRESS COMMERCIAL'
}
