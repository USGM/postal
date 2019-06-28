"""
This is the module for interfacing with DHL's web services APIs.

DHL has declined to provide a WSDL file for their web services. While they do
provide XSL files which could be used to generate Python classes to manipulate,
the result is a workflow that is still too unfavorable in the cost/benefit
department.

So, instead, we use a set of templates and populate these to make the final
request.

These templates are currently glorified Python strings. In the future, these should
be replaced with something like Djinja templates.

DHL rarely ships domestically, and trying to handle domestic shipments with
them results in a lot of traps. We therefore disable domestic shipments with
DHL.
"""
from collections import OrderedDict
from decimal import Decimal
from io import BytesIO
from math import ceil
from pprint import pformat
import random
from base64 import b64decode
from datetime import datetime
from time import timezone
from xml.etree.ElementTree import fromstring
from xml.sax.saxutils import escape
from dateutil import parser

from PyPDF2 import PdfFileReader, PdfFileWriter
from dateutil.relativedelta import relativedelta

from money import Money
from postal.data import Address, country_map
from requests import post, RequestException

import pycountry

from .base import Carrier, PostalLogger
from .templates.constructor import load_template, populate_template
from ..exceptions import CarrierError, NotSupportedError, SoftCarrierError
from ..data import Shipment, TWOPLACES, sigfig

class DHLApi(Carrier):
    name = 'DHL'
    domestic = False

    _code_to_description = {
        #'N': 'Domestic Express',
        #'K': 'Domestic 09:00',
        #'T': 'Domestic 12:00',

        'U': 'Express Worldwide',
        'D': 'Express Worldwide',
        'P': 'Express Worldwide',

        'K': 'Express 09:00',
        'E': 'Express 09:00',

        'T': 'Express 12:00',
        'Y': 'Express 12:00',

        'L': 'Express 10:30',
        'M': 'Express 10:30',

        'H': 'Economy Select',
        'W': 'Economy Select',
        'X': 'Express Envelope'}

    _generic_package_translation = {
        'softpak': 'CP',
        'package': 'CP'}

    _to_proprietary_packaging = {
        'envelope': 'EE',
        'softpak': 'OD'}

    _package_id_to_description = {
        'EE': 'Express Envelope',
        'OD': 'Other Packaging'}

    # Aside from Economy, DHL's transit times are mostly the same.
    _min_max_estimates = {key: (1, 3)
                          for key in _code_to_description.keys()}
    _min_max_estimates['H'] = (2, 5)
    _min_max_estimates['W'] = (2, 5)

    def __init__(
            self, account_number, region_code, company_name, site_id,
            password, test_mode=False, rates_url=None, insecure_rates=False,
            postal_configuration=None):
        super(DHLApi, self).__init__(postal_configuration)
        self.site_id = site_id
        self.password = password
        self.account_number = account_number
        self.region_code = region_code
        self.company_name = company_name
        self.insecure_rates = insecure_rates

        if test_mode:
            self.url = 'https://xmlpitest-ea.dhl.com/XMLShippingServlet'
        else:
            self.url = 'https://xmlpi-ea.dhl.com/XMLShippingServlet'

        if not rates_url:
            self.rates_url = self.url
        else:
            self.rates_url = rates_url

    def make_call(self, call, rates=False):
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "Close"}
        call = u'%s' % call
        call = call.encode('utf-8')
        if rates:
            url = self.rates_url
        else:
            url = self.url
        try:
            response = post(
                url, data=call, headers=headers,
                timeout=self.postal_configuration['timeout'])
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)

        with self.logger.lock:
            self.logger.sent(call)
            self.logger.received(response.text)

        root = fromstring(u'%s' % response.text)
        # DHL has about three or four ways to send an error message.
        response = root
        response_tag = response.find('Response')
        if response_tag is not None:
            response = response_tag
        error_tag = None
        note = response.find('Note')
        status = response.find('Status')
        condition = None
        if note is not None:
            error_tag = note
        if status is not None:
            error_tag = status
        if error_tag is not None:
            if not ((error_tag.findtext('ActionStatus') == 'Success')
                    or (error_tag.findtext('ActionNote') == 'Success')):
                condition = error_tag.find('Condition')
        if condition is not None:
            raise CarrierError("%s" % condition.findtext('ConditionData'),
                               code=condition.findtext('ConditionCode'))
        return root

    @staticmethod
    def get_price(quote):
        prices = quote.findall('QtdSInAdCur')
        # We pick BILLC as the canonical price, since it's the one that would
        # actually be billed.
        correct_price = None
        for price in prices:
            if price.findtext('CurrencyRoleTypeCode') == 'BILLC':
                correct_price = price
            if correct_price is not None:
                break
        if correct_price is None or correct_price.find('CurrencyCode') is None:
            raise CarrierError(
                "DHL gave a nonsense response to a pricing request.")
        currency = correct_price.find('CurrencyCode').text
        total = correct_price.find('TotalAmount').text
        total = Money(Decimal(total).quantize(Decimal('0.01')), currency)
        base_price = correct_price.find('WeightCharge').text
        base_price = Money(Decimal(base_price).quantize(Decimal('0.01')), currency)
        return {'total': total, 'base_price': base_price, 'fees': (total - base_price)}

    @staticmethod
    def from_timestr(time_string):
        if not time_string:
            return None
        time = None
        try:
            time = datetime.strptime(time_string, '%Y-%m-%d')
        except ValueError:
            pass
        try:
            time = datetime.strptime(time_string, '%Y-%m-%dPT%HH%MM')
        except ValueError:
            pass
        return time

    @staticmethod
    def make_datetime_string(time=None):
        time = time or datetime.now()
        offset = DHLApi.timezone_offset()
        time = time.strftime('%Y-%m-%dT%H:%M:%S')
        return "%s%s" % (time, offset)

    @staticmethod
    def ref_number():
        """
        Generate reference number for request.
        """
        return str(random.randrange(
            1000000000000000000000000000, 9999999999999999999999999999))

    @staticmethod
    def response_to_dict(quotes):
        response_dict = {}
        for quote in quotes:
            key = quote.findtext('GlobalProductCode')
            if not key:
                continue
            try:
                response_dict[key] = {
                    'service_name': quote.find(
                        'LocalProductName').text.title(),
                    'delivery_datetime': DHLApi.from_timestr(
                        quote.findtext('DeliveryDate') or ''
                        + quote.findtext('DeliveryTime') or ''),
                    'price': DHLApi.get_price(quote),
                    'trackable': True}
            except CarrierError:
                continue
        return response_dict

    def get_services(self, request):
        self._ensure_supported(request)

        response_dict = self.get_from_cache(request, 'dhl')
        if not response_dict:
            rate_request = self.rates_request(request)

            with self.logger.lock:
                self.logger.debug_header('Get Services')
                self.logger.debug(request)

            response = self.make_call(rate_request, rates=True)[0][1]
            response_dict = self.response_to_dict(response.findall('QtdShp'))
            self.cache_results(request, response_dict, 'dhl')

        result = {
            self.get_service(key): {
                'price': value['price'],
                'delivery_datetime': value['delivery_datetime'],
                'trackable': True}
            for key, value in response_dict.items()}

        with self.logger.lock:
            self.logger.debug_header('Response')
            self.logger.debug(pformat(result, width=1))

        return result

    @staticmethod
    def build_address(address, company_name=None):
        company_name = company_name or address.contact_name
        template = load_template('dhl', 'address_line.xml')
        lines = []
        for line in address.street_lines:
            lines.append(populate_template(template, {'line': line}))
        lines = ''.join(lines)
        template = load_template('dhl', 'address.xml')
        return populate_template(
            template,
            {'city': address.city,
             'subdivision': address.subdivision,
             'postal_code': address.postal_code,
             'phone_number': address.phone_number,
             'contact_name': address.contact_name,
             'country_code': address.country.alpha2,
             'country_name': address.country.name,
             'company_name': company_name},
            {'lines': lines})

    def create_header(self, rates=False):
        message_time = self.make_datetime_string()
        message_reference = self.ref_number()
        template = load_template('dhl', 'header.xml')
        if rates and self.insecure_rates:
            site_id = 'XXX'
            password = 'XXX'
        else:
            site_id = self.site_id
            password = self.password
        return populate_template(template, {
            'message_time': message_time,
            'message_reference': message_reference,
            'site_id': site_id, 'password': password})

    @staticmethod
    def timezone_offset():
        offset = relativedelta(seconds=timezone)
        tz_hour = offset.hour or 0
        tz_min = offset.minute or 0
        if (tz_hour, tz_min) == (abs(tz_hour), abs(tz_min)):
            tz_sign = '+'
        else:
            tz_sign = '-'

        tz_hour = "%02d" % abs(tz_hour)
        tz_min = "%02d" % abs(tz_min)
        return "%s%s:%s" % (tz_sign, tz_hour, tz_min)

    @staticmethod
    def contents(request):
        """
        Get the contents of the packages and make a summarizing string.
        """
        summary = ''
        if request.documents_only():
            return 'Noncommercial Documents'
        for package in request.packages:
            for declaration in package.declarations:
                summary += "%s %sx," % (
                    declaration.description, declaration.units)
        summary = summary[:-1]
        return summary[:90]

    @staticmethod
    def money_snippet(template_name, request, insurance):
        template = load_template('dhl', template_name)
        for package in request.packages:
            if not package.declarations and not request.documents_only():
                raise NotSupportedError(
                    "DHL requires all packages to have declarations.")

        if insurance:
            money = request.get_total_insured_value()
        else:
            money = request.get_total_declared_value()
        if not money and not insurance:
            return ''

        return populate_template(
            template, {
                'currency': money.currency,
                'value': money.amount.quantize(TWOPLACES)})

    @staticmethod
    def enumerate_pieces(template_name, request):
        result = []
        template = load_template('dhl', template_name)
        for number, package in enumerate(request.packages):
            result.append(populate_template(
                template, {
                    'length': int(ceil(package.length)),
                    'width': int(ceil(package.width)),
                    'height': int(ceil(package.height)),
                    'weight': sigfig(package.weight),
                    'number': number + 1}))
        return ''.join(result)

    def rates_request(self, request):
        origin = request.origin or self.postal_configuration['shipper_address']

        request_header = self.create_header(rates=True)

        pieces = self.enumerate_pieces('rates_piece.xml', request)

        duties = self.money_snippet('rates_dutiable.xml', request, False)
        request_template = load_template('dhl', 'rates.xml')
        ship_datetime = request.ship_datetime or datetime.now()
        ship_date = ship_datetime.strftime('%Y-%m-%d')
        hour = ship_datetime.hour
        minute = ship_datetime.minute
        if request.documents_only():
            is_dutiable = 'N'
        else:
            is_dutiable = 'Y'
        tz_offset = self.timezone_offset()
        if request.destination.city:
            destination_city = '<City>%s</City>' % (
                request.destination.city.upper())
        else:
            destination_city = ''
        if request.extra_params.get('retail_rate'):
            account_number = ''
        else:
            account_number = '<PaymentAccountNumber>{}</PaymentAccountNumber>'.format(self.account_number)

        if origin.city:
            origin_city = '<City>%s</City>' % origin.city.upper()
        else:
            origin_city = ''

        escape_variables = {
            'origin_country': origin.country.alpha2,
            'origin_postal_code': origin.postal_code,
            'ship_date': ship_date,
            'hour': hour,
            'minute': minute,
            'is_dutiable': is_dutiable,
            'destination_country': request.destination.country.alpha2,
            'destination_postal_code': request.destination.postal_code,
            'tz_offset': tz_offset
        }
        non_escape_variables = {
            'account_number': account_number,
            'duties': duties,
            'pieces': pieces,
            'destination_city': destination_city,
            'origin_city': origin_city,
            'request_header': request_header,
            'insured': self.money_snippet('insured.xml', request, True)}
        request = populate_template(
            request_template, escape_variables, non_escape_variables)
        return request

    def track_request(self, identifier):
        track_template = load_template('dhl', 'track.xml')
        escape_variables = {'tracking_number': identifier}
        non_escape_variables = {'request_header': self.create_header()}

        return populate_template(
            track_template, escape_variables, non_escape_variables)

    def shipment_request(self, service, request, paperless=True):
        ship_template = load_template('dhl', 'ship.xml')
        ship_datetime = request.ship_datetime or datetime.now()
        ship_date = ship_datetime.strftime('%Y-%m-%d')

        origin = request.origin or self.postal_configuration['shipper_address']
        origin_address = self.build_address(origin, self.company_name)
        destination_address = self.build_address(request.destination)

        total_weight = sum([package.weight for package in request.packages])

        insured = request.get_total_insured_value()

        if request.documents_only():
            is_dutiable = 'N'
            commercial_invoice = ''
            special_services = ''
        else:
            is_dutiable = 'Y'
            invoice_template = load_template('dhl', 'commercial_invoice.xml')
            if paperless:
                commercial_invoice = populate_template(
                    invoice_template,
                    {'invoice': self.commercial_invoice(request)})
                special_services = '<SpecialService><SpecialServiceType>WY' \
                                   '</SpecialServiceType></SpecialService>'
            else:
                commercial_invoice = ''
                special_services = ''

        if request.extra_params.get('dhl_duties_account', False):
            duties_payment = 'T'
            duties_account = (
                '<DutyAccountNumber>%s</DutyAccountNumber>'
                % escape(request.extra_params['dhl_duties_account']))
        else:
            duties_payment = 'R'
            duties_account = ''

        escape_variables = {
            'origin_country': origin.country.alpha2,
            'origin_postal_code': origin.postal_code,
            'ship_date': ship_date,
            'destination_country': request.destination.country.alpha2,
            'destination_postal_code': request.destination.postal_code,
            'account_number': self.account_number,
            'number_of_packages': len(request.packages),
            'total_weight': total_weight,
            'region_code': self.region_code,
            'default_currency': self.postal_configuration['default_currency'],
            'contents': self.contents(request),
            'is_dutiable': is_dutiable,
            'duties_payment': duties_payment,
            'product_code': service.service_id}
        non_escape_variables = {
            'origin_address': origin_address,
            'destination_address': destination_address,
            'duties': self.money_snippet('ship_dutiable.xml', request, False),
            'pieces': self.enumerate_pieces('ship_piece.xml', request),
            'request_header': self.create_header(),
            'insured_amount': insured.amount.quantize(TWOPLACES),
            'insured_currency': insured.currency,
            'commercial_invoice': commercial_invoice,
            'duties_account': duties_account,
            'special_services': special_services}

        request = populate_template(
            ship_template, escape_variables, non_escape_variables)
        return request

    @staticmethod
    def format_labels(data):
        if isinstance(data, str):
            data = b64decode(data.encode('utf-8'))
        else:
            data = b64decode(data)
        main_pdf = PdfFileReader(BytesIO(data))
        num_pages = main_pdf.getNumPages()
        labels = []
        for page in range(num_pages - 1):
            output = PdfFileWriter()
            page = main_pdf.getPage(page)
            page.mediaBox.UpperRight = (41, 47)
            page.mediaBox.LowerLeft = (322, 580)
            output.addPage(page)
            output_stream = BytesIO()
            output.write(output_stream)
            # Reload page for resizing.
            labels.append(output_stream.getvalue())
        return labels

    def _ensure_supported(self, request):
        if request.destination.country == self.get_origin(request).country:
            raise NotSupportedError("DHL does not support domestic shipments.")

        for pak in request.packages:
            envelope = all([pak.package_type.carrier is None,
                            pak.package_type.code == 'envelope',
                            pak.carrier_conversion])
            express = all([pak.package_type.carrier == self,
                           pak.package_type.code == 'EE'])

            if envelope and express:
                # express envelope or generic conversion to one
                if pak.weight > .5:
                    raise NotSupportedError('DHL does not ship express '
                                            'envelopes that weigh more than '
                                            '.5 pounds.')

    @staticmethod
    def get_shipping_charge(response):
        charge = response.findtext('ShippingCharge')
        currency = response.findtext('CurrencyCode')
        return Money(charge, currency)

    def track(self, identifier):
        track_request = self.track_request(identifier)
        with self.logger.lock:
            self.logger.debug_header('Tracking')
            self.logger.debug(identifier)

        response = self.make_call(track_request)

        result = {
            'delivered': False,
            'finalized': False,
            'status_code': u'',
            'description': u'',
            'event_time': None,
            'location': False
        }

        if response.find('AWBInfo').find('ShipmentInfo') is not None:
            events = response.find('AWBInfo').find('ShipmentInfo').findall('ShipmentEvent')
            if len(events):
                details = events[-1]
                event = details.find('ServiceEvent')
                event_code = event.findtext('EventCode')
                event_time = parser.parse(details.findtext('Date') + ' ' + details.findtext('Time'))
                result = {
                    'delivered': event_code == 'OK',
                    'finalized': event_code in ['OK'],
                    'status_code': u'{}'.format(event_code),
                    'description': u'{}'.format(event.findtext('Description')),
                    'event_time': event_time
                }
                street = [' ']
                city_country = details.find('ServiceArea').findtext('Description').split('-')
                if len(city_country) == 3:
                    city, place, country = city_country
                    city = "{city} - {place}".format(city=city, place=place)
                else:
                    city, country = city_country
                try:
                    country = country_map[country.lower()].alpha2
                except KeyError:
                    try:
                        country = pycountry.countries.get(alpha3=country).alpha2
                    except KeyError:
                        # By some reason DHL returns NGR code for Nigeria instead NGA
                        if country == "NGR":
                            country = pycountry.countries.get(alpha3="NGA")
                        else:
                            with self.logger.lock:
                                self.logger.error("Unknown country received during tracking: {}".format(country))
                result['location'] = Address(
                    street_lines=street,
                    city=u'{}'.format(city),
                    country=country,
                )
        else:
            condition = response.find('AWBInfo').find('Status').find('Condition')
            conditionCode = condition.findtext('ConditionCode')
            conditionData = condition.findtext('ConditionData')
            if conditionCode == '209':
                raise SoftCarrierError(u"{}".format(conditionData))
            result['status_code'] = u'{}'.format(conditionCode)
            result['description'] = u'{}'.format(conditionData)
        return result

    def ship(self, service, request):
        # DHL's shipment rating information from their shipment API is bogus.
        # The rating API is the most trustworthy.
        price = self.quote(service, request)
        self._ensure_supported(request)
        ship_request = self.shipment_request(service, request)
        alerts = []

        with self.logger.lock:
            self.logger.debug_header('Shipment')
            self.logger.debug(service)
            self.logger.debug(request)

        try:
            response = self.make_call(ship_request)
        except CarrierError as err:
            if err.code and err.code.startswith('PLT'):
                ship_request = self.shipment_request(
                    service, request, paperless=False)
                response = self.make_call(ship_request)
                alerts.append(
                    'Could not send paperless invoice. Please print and '
                    'attach a commercial invoice to this shipment.')
            else:
                raise err
        tracking_number = response.findtext('AirwayBillNumber')
        labels = response.findtext('LabelImage/OutputImage')
        if not labels:
            raise CarrierError('DHL generated no labels.')
        labels = self.format_labels(labels)

        package_details = OrderedDict(
            (package, {'label': label, 'tracking_number': tracking_number})
            for package, label in zip(request.packages, labels)
        )
        shipment_dict = {
            'shipment': Shipment(self, tracking_number),
            'packages': package_details,
            'price': price,
            'alerts': alerts}

        with self.logger.lock:
            self.logger.debug_header('Response')
            self.logger.shipment_response(shipment_dict)

        return shipment_dict

    def delivery_datetime(self, service, request):
        self._ensure_supported(request)
        data = self.get_from_cache(request, 'dhl')
        if not data:
            self.get_services(request)
        data = self.get_from_cache(request, 'dhl').get(service.service_id, None)
        if not data:
            raise NotSupportedError("DHL does not support shipment of that package(s).")
        return data['delivery_datetime']

    def quote(self, service, request):
        self._ensure_supported(request)
        data = self.get_from_cache(request, 'dhl')
        if not data:
            self.get_services(request)
        data = self.get_from_cache(request, 'dhl').get(service.service_id, None)
        if not data:
            raise NotSupportedError("DHL does not support shipment of that package(s).")
        return data['price']


# DHL product code (
# D : US Overnight (>0.5 lb) and Worldwide Express Non-dutiable (>0.5 lb) ,

# X : USA Express Envelope (less
# than or = 0.5 lb) and Worldwide Express-International Express Envelope (less
# than or = 0.5 lb),

# W : Worldwide Express-Dutiable,

# Y : DHL Second Day
# Express . Must be Express Envelop with weight lessthan or = 0.5 lb,

# G : DHL Second Day . Weight > 0.5 lb or not an express envelop,

# T : DHL Ground Shipments)
