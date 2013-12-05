"""
This is the module for interfacing with DHL's web services APIs.

DHL has declined to provide a WSDL file for their web services. While they do
provide XSL files which could be used to generate Python classes to manipulate,
the result is a workflow that is still too unfavorable in the cost/benefit
department.

So, instead, we use a set of templates and populate these to make the final
request.

DHL rarely ships domestically, and trying to handle domestic shipments with
them results in a lot of traps. We therefore disable domestic shipments with
DHL.
"""
from base64 import b64decode
from datetime import datetime
from time import timezone
from xml.etree.ElementTree import fromstring

from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from dateutil.relativedelta import relativedelta
from money import Money
from requests import post, RequestException

from base import Carrier, Service
from ..carriers.templates.constructor import load_template, populate_template
from ..exceptions import ExceedsLimitsError, CarrierError
from ..data import Shipment


class DHLApi(Carrier):
    name = 'DHL'
    domestic = False
    def __init__(
            self, account_number, region_code, company_name, default_currency,
            site_id, password, test_mode=False):
        super(DHLApi, self).__init__()
        self.site_id = site_id
        self.password = password
        self.account_number = account_number
        self.region_code = region_code
        self.company_name = company_name
        self.default_currency = default_currency

        if test_mode:
            self.url = 'https://xmlpitest-ea.dhl.com/XMLShippingServlet'
        else:
            self.url = 'https://xmlpi-ea.dhl.com/XMLShippingServlet'

    def make_call(self, call):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = post(self.url, data=call, headers=headers)
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)
        root = fromstring(response.text)
        # DHL has about three or four ways to send an error message.
        error_tag = None
        note = root.find('Note')
        status = root.find('Status')
        condition = None
        if note is not None:
            error_tag = note
        if status is not None:
            error_tag = status
        if error_tag is not None:
            if not error_tag.findtext('ActionNote') == 'Success':
                condition = error_tag.find('Condition')
        if condition is not None:
            raise CarrierError("Error %s. %s" % (
                condition.findtext('ConditionCode'),
                condition.findtext('ConditionData')))
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
        if correct_price is None:
            raise CarrierError(
                "DHL gave a nonsense response to a pricing request.")
        currency = correct_price.find('CurrencyCode').text
        amount = correct_price.find('TotalAmount').text
        return Money(amount, currency)

    @staticmethod
    def from_timestr(time_string):
        return datetime.strptime(time_string, '%Y-%m-%dPT%HH%MM')

    @staticmethod
    def make_datetime_string(time=None):
        time = time or datetime.now()
        offset = DHLApi.timezone_offset()
        time = time.strftime('%Y-%m-%dT%H:%M:%S')
        return "%s%s" % (time, offset)

    @staticmethod
    def ref_number():
        """
        This is useless, but required.
        """
        return "1111111111111111111111111111"

    @staticmethod
    def response_to_dict(quotes):
        return {
            quote.find('GlobalProductCode').text: {
                'service_name': quote.find('LocalProductName').text.title(),
                'delivery_datetime': DHLApi.from_timestr(
                    quote.find('DeliveryDate').text
                    + quote.find('DeliveryTime').text),
                'price': DHLApi.get_price(quote)}
            for quote in quotes}

    def get_services(self, request):
        pieces = self.enumerate_pieces('rates_piece.xml', request)
        duties = self.money_snippet('rates_dutiable.xml', request)

        rate_request = self.rates_request(request)
        response = self.make_call(rate_request)[0][1]
        response_dict = self.response_to_dict(response.findall('QtdShp'))
        self.cache_results(request, response_dict)
        return {
            Service(self, key, value['service_name']): {
                'price': value['price'],
                'delivery_datetime': value['delivery_datetime']}
            for key, value in response_dict.items()}

    @staticmethod
    def build_address(address):
        template = load_template('dhl', 'address_line.xml')
        lines = []
        for line in address.street_lines:
            lines.append(populate_template(template, {'line': line}))
        lines = ''.join(lines)
        template = load_template('dhl', 'address.xml')
        return populate_template(
            template, {
                'city': address.city,
                'subdivision': address.subdivision,
                'postal_code': address.postal_code,
                'phone_number': address.phone_number,
                'contact_name': address.contact_name,
                'country_code': address.country.alpha2,
                'country_name': address.country.name},
            {'lines': lines})

    def create_header(self):
        message_time = self.make_datetime_string()
        message_reference = self.ref_number()
        template = load_template('dhl', 'header.xml')
        return populate_template(template, {
            'message_time': message_time,
            'message_reference': message_reference,
            'site_id': self.site_id, 'password': self.password})

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
        for package in request.packages:
            for declaration in package.declarations:
                summary += "%s %sx," % (
                    declaration.description, declaration.units)
        summary = summary[:-1]
        return summary[:90]

    @staticmethod
    def money_snippet(template_name, request):
        template = load_template('dhl', template_name)
        money = None
        for package in request.packages:
            if not package.declarations:
                print package.__dict__
                raise CarrierError(
                    "All packages must have declarations with DHL.")
            for declaration in package.declarations:
                if not money:
                    money = declaration.value
                else:
                    money += declaration.value
        if not money:
            return ''
        return populate_template(
            template, {
                'currency': money.currency, 'value': money.amount})

    @staticmethod
    def enumerate_pieces(template_name, request):
        result = []
        template = load_template('dhl', template_name)
        for number, package in enumerate(request.packages):
            result.append(populate_template(
                template, {
                    'length': package.length, 'width': package.width,
                    'height': package.height, 'weight': package.weight,
                    'number': number + 1}))
        return ''.join(result)

    def rates_request(self, request):
        request_header = self.create_header()
        pieces = self.enumerate_pieces('rates_piece.xml', request)
        duties = self.money_snippet('rates_dutiable.xml', request)
        request_template = load_template('dhl', 'rates.xml')
        ship_datetime = request.ship_datetime or datetime.now()
        ship_date = ship_datetime.strftime('%Y-%m-%d')
        hour = ship_datetime.hour
        minute = ship_datetime.minute
        if request.insure:
            insured = self.money_snippet('insured.xml', request)
        else:
            insured = ''
        tz_offset = self.timezone_offset()
        escape_variables = {
            'origin_country': request.origin.country.alpha2,
            'origin_postal_code': request.origin.postal_code,
            'ship_date': ship_date,
            'hour': hour,
            'minute': minute,
            'destination_country': request.destination.country.alpha2,
            'destination_postal_code': request.destination.postal_code,
            'tz_offset': tz_offset}
        non_escape_variables = {
            'duties': duties,
            'pieces': pieces,
            'request_header': request_header,
            'insured': insured}
        return populate_template(
            request_template, escape_variables, non_escape_variables)

    def shipment_request(
            self, request):
        request_header = self.create_header()
        duties = self.money_snippet('ship_dutiable.xml', request)
        pieces = self.enumerate_pieces('ship_piece.xml', request)
        ship_template = load_template('dhl', 'ship.xml')
        ship_datetime = request.ship_datetime or datetime.now()
        ship_date = ship_datetime.strftime('%Y-%m-%d')
        if request.insure:
            insured = self.money_snippet('insured.xml', request)
        else:
            insured = ''

        origin_address = self.build_address(request.origin)
        destination_address = self.build_address(request.destination)
        number_of_packages = len(request.packages)

        contents = self.contents(request)

        total_weight = sum([package.weight for package in request.packages])

        escape_variables = {
            'origin_country': request.origin.country.alpha2,
            'origin_postal_code': request.origin.postal_code,
            'ship_date': ship_date,
            'destination_country': request.destination.country.alpha2,
            'destination_postal_code': request.destination.postal_code,
            'account_number': self.account_number,
            'number_of_packages': number_of_packages,
            'total_weight': total_weight,
            'region_code': self.region_code,
            'company_name': self.company_name,
            'default_currency': self.default_currency,
            'contents': contents}
        non_escape_variables = {
            'origin_address': origin_address,
            'destination_address': destination_address,
            'duties': duties,
            'pieces': pieces,
            'request_header': request_header,
            'insured': insured}

        return populate_template(
            ship_template, escape_variables, non_escape_variables)

    @staticmethod
    def format_labels(data):
        main_pdf = PdfFileReader(StringIO(b64decode(data)))
        num_pages = main_pdf.getNumPages()
        labels = []
        for page in range(num_pages - 1):
            output = PdfFileWriter()
            page = main_pdf.getPage(page)
            page.mediaBox.UpperRight = (41, 47)
            page.mediaBox.LowerLeft = (322, 580)
            output.addPage(page)
            output_stream = StringIO()
            output.write(output_stream)
            # Reload page for resizing.
            labels.append(output_stream.getvalue())
        return labels

    def ship(self, service, request):
        ship_request = self.shipment_request(
            request)
        response = self.make_call(ship_request)
        tracking_number = response.findtext('AirwayBillNumber')
        labels = response.findtext('LabelImage/OutputImage')
        labels = self.format_labels(labels)
        package_details = {
            package: {'label': label, 'tracking_number': tracking_number}
            for package, label in zip(request.packages, labels)}
        return Shipment(self, tracking_number, package_details)

    def delivery_datetime(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[tuple(request)].get(service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return data['delivery_datetime']

    def quote(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[self.cache_key(request)].get(
            service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return Money(data['price'].amount, data['price'].currency)