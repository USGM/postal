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
from pprint import pprint
import re
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
from xml.sax.saxutils import unescape
from postal.data import Request


class USPSApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    name = 'USPS'
    multiship = False

    _code_to_description = {
        'PRIORITY:DEFAULT': 'Priority',
        'PRIORITY:FLAT RATE ENVELOPE': 'Priority Mail - Flat Rate Envelope',
        'PRIORITY:LEGAL FLAT RATE ENVELOPE': 'Priority Mail - '
                                             'Legal Flat Rate Envelope',
        'PRIORITY:PADDED FLAT RATE ENVELOPE': 'Priority Mail - '
                                              'Padded Flat Rate Envelope',

        'STANDARD POST:DEFAULT': 'Standard Post',
        'EXPRESS:DEFAULT': 'Priority Mail Express',
        'EXPRESS:FLAT RATE ENVELOPE': 'Priority Mail Express - '
                                      'Flat Rate Envelope',
        'EXPRESS:LEGAL FLAT RATE ENVELOPE': 'Priority Mail Express - '
                                            'Legal Flat Rate Envelope',
        'EXPRESS:PADDED FLAT RATE ENVELOPE': 'Priority Mail Express - '
                                             'Padded Flat Rate Envelope',
        'FIRST CLASS:DEFAULT': 'First-Class Mail',
        'FIRST CLASS:PARCEL': 'First-Class Mail - Parcel',
        'FIRST CLASS:LARGE ENVELOPE': 'First-Class Mail - Large Envelope'}

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
    def make_call(url, api, call):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = post(
                url, data={'API': api, 'XML': call}, headers=headers)
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)
        root = fromstring(response.text)

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

        if root.tag == 'Error':
            raise CarrierError('Error #%s. %s' % (
                root.find('Number').text,
                root.find('Description').text))
        return root

    @staticmethod
    def ship_date(date_time):
        return date_time.strftime('%d-%b-%Y')

    def get_services(self, request):
        self._ensure_supported(request)

        origin = request.origin or self.postal_configuration['shipper_address']

        if request.destination.country.alpha2 == 'US':
            return self._get_rates_domestic(request, origin)
        else:
            return self._get_rates_international(request, origin)

    @staticmethod
    def _get_insurance_price(service_tag, request):
        print tostring(service_tag)
        for extra_service in service_tag.find('ExtraServices'):
            if extra_service.find('ServiceID').text.strip() != '1':
                # 1 = insurance
                continue
            if extra_service.find('OnlineAvailable') \
                    .text.strip().lower() != 'true':
                continue
            insured_value = request.get_total_insured_value()
            price = Money(
                extra_service.find('PriceOnline').text, 'USD')
            insurance_price = price * ceil(
                insured_value.amount / 100)
            return insurance_price

    @classmethod
    def _desc_from_tag(cls, service_tag):
        desc = cls._code_to_description.get(service_tag.get('ID'), None)
        if not desc:
            desc = "%s**%s" % (
                service_tag.get('ID'),
                unescape(unescape(service_tag.find('SvcDescription').text)))
        return desc

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
            'container': container}

        package_escape, package_nonescape = self._get_package_parameters(
            request.packages[0], 0, origin, request.destination)
        escape_dict.update(package_escape)

        escape_dict['value'] = request.get_total_insured_value().amount

        non_escape_dict = package_nonescape
        call = populate_template(
            load_template('usps', 'rates_international.xml'),
            escape_dict, non_escape_dict)
        response = self.make_call(self.rate_url, 'IntlRateV2', call)

        result = {}
        for service_tag in response.find('Package').iterfind('Service'):
            insurance_price = self._get_insurance_price(service_tag, request)
            if (request.get_total_insured_value() > 0 and
                    insurance_price is None):
                continue

            if insurance_price is None:
                insurance_price = Money(0, 'USD')

            service_code = 'I' + service_tag.get('ID')
            service = Service(self, service_code, self._desc_from_tag(
                service_tag))

            if request.destination.residential:
                postage_tag = 'Postage'
            else:
                postage_tag = 'CommercialPostage'

            postage_tag = service_tag.find(postage_tag)
            price = Money(postage_tag.text, 'USD') + insurance_price

            result[service] = {'price': price, 'delivery_datetime': None}

        return result

    def _enumerate_package(self, request, origin, ship_date):
        template = load_template('usps', 'package_domestic.xml')
        packages = ''
        services = [
            'ALL', 'PRIORITY COMMERCIAL', 'FIRST CLASS COMMERCIAL']
        for index, service in enumerate(services):
            escape_dict, non_escape_dict = self._get_package_parameters(
                request.packages[0], index, origin, request.destination,
                ship_date=ship_date, service=service)
            packages += populate_template(
                template, escape_dict, non_escape_dict)
        return packages

    @staticmethod
    def _get_package_parameters(
            package, index, origin, destination,
            ship_date=None, service='ALL'):
        """
        returns: (escape:{...}, nonescape:{...})
        """
        international = (origin.country != destination.country)
        if international and package.get_total_insured_value() > 0:
            insurance = '<ExtraServices><ExtraService>1' \
                        '</ExtraService></ExtraServices>'
        else:
            ### Special Services prices and availability will not be returned
            ### when Service = "ALL" or "ONLINE"
            insurance = ''

        length, width, height = sorted(
            [package.width, package.height, package.length])
        if length > 12 or international:
            size = 'LARGE'
            container = 'RECTANGULAR'
        else:
            size = 'REGULAR'
            container = 'VARIABLE'

        girth = (width + height) * 2

        pounds = int(floor(package.weight))
        ounces = int(ceil((package.weight - pounds) * 16))

        if international:
            value = package.get_total_declared_value().amount
        else:
            value = package.get_total_insured_value().amount

        return (
            {'service': service, 'origin_zip': origin.postal_code,
             'destination_zip': destination.postal_code, 'length': length,
             'width': width, 'height': height, 'pounds': pounds,
             'ounces': ounces, 'id': index, 'size': size,
             'container': container, 'girth': girth,
             'value': value, 'ship_date': ship_date},
            {'insurance': insurance})

    @staticmethod
    def _derive_code(text):
        """
        USPS provides no service table chart, so the service class IDs are not
        very useful. One can, however, derive the service and required
        packaging based on their information string.

        This would be the wrong way to do things, if there were a right way.
        """
        text = unescape(text)
        # This doesn't replace one tag. It clears everything from the first
        # open bracket to the last closing one.
        text = re.sub('<.+>', ':', text)
        parts = text.split(':')
        parts.reverse()
        text = parts.pop()
        try:
            method = parts.pop()
        except IndexError:
            method = 'DEFAULT'
        text = re.sub(r'[^\w]', ' ', text)
        text = re.sub(r'[\d] day', '', text, flags=re.IGNORECASE)
        text = text.upper()
        if 'PRIORITY' in text or 'FIRST CLASS' in text:
            text = re.sub(' MAIL ?', '', text)
        if 'EXPRESS' in text:
            text = text.replace('PRIORITY', '')
        text = text.strip()
        method = method.strip().upper()
        if not method:
            method = 'DEFAULT'

        return "%s:%s" % (text, method)

    def _get_rates_domestic(self, request, origin):

        ship_date = self.ship_date(request.ship_datetime or datetime.now())

        packages = self._enumerate_package(
            request, origin, ship_date)

        escape_dict = {
            'user_id': self.user_id,
            'origin_zip': origin.postal_code,
            'destination_zip': request.destination.postal_code,
            'ship_date': ship_date,
            'value': request.get_total_insured_value().amount}
        non_escape_dict = {
            'packages': packages}
        call = populate_template(
            load_template('usps', 'rates_domestic.xml'),
            escape_dict, non_escape_dict)

        response = self.make_call(self.rate_url, 'RateV4', call)

        result = {}
        for package_tag in response.iterfind('Package'):
            # A package may have multiple service ratings.
            for service_tag in package_tag.iterfind('Postage'):
                service_code = self._derive_code(
                    service_tag.findtext('MailService'))
                print service_code
                service_desc = self._code_to_description.get(service_code, None)
                if not service_desc:
                    continue
                service = Service(self, service_code, service_desc)

                delivery = service_tag.find('CommitmentDate')
                if delivery is not None:
                    delivery = delivery.text.split('-')
                    delivery = datetime(
                        year=int(delivery[0]),
                        month=int(delivery[1]),
                        day=int(delivery[2]),
                        hour=23,
                        minute=59)

                result[service] = {
                    'price': Money(service_tag.find('Rate').text, 'USD'),
                    'delivery_datetime': delivery}
        if request.get_total_insured_value() > 0:
            print "I ran!"
            insurance_request = request.shallow_copy()
            insurance_request.packages = []
            insurance_services = []

            ### TODO: find a more robust solution than clipping the
            # list
            #if len(list(result.items())) > 25:
            #   raise Exception()

            # limited to 25 packages
            #for service, info in list(result.items())[:25]:
                # Not supporting external queries of more than one
                # package
            #    insurance_request.packages.append(request.packages[0])
            #    insurance_services.append(
            #        _short_to_long_code[service.service_id])

                # Service must be Priority Express, Priority Express
                # SH, Priority Express Commercial, Priority Express SH
                # Commercial, First Class, Priority, Priority
                # Commercial, Standard Post, Library, BPM, Media,
                # ALL, or ONLINE

        pprint(result)
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