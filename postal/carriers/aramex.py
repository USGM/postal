from multiprocessing.pool import ThreadPool

from base64 import b64decode
from xml.etree.ElementTree import iterparse

from StringIO import StringIO

from dateutil import parser
from postal.data import Address, country_map
from suds.client import Client, TypeNotFound
from money import Money

from postal.carriers.base import Carrier, ClearEmpty, PostalLogger
from postal.exceptions import CarrierError, AddressError
from datetime import datetime
from postal.data import Package
from copy import deepcopy
from ..data import Shipment
from collections import OrderedDict
from decimal import Decimal
from pprint import pformat
import warnings
from io import BytesIO
from PyPDF2 import PdfFileReader, PdfFileWriter
from PyPDF2.utils import PdfReadWarning


TWOPLACES = Decimal('0.01')
logger = PostalLogger(carrier_name='Aramex')
warnings.filterwarnings("ignore", category=PdfReadWarning)


class AramexApi(Carrier):
    """
    Implements calls to the aramex api.
    """
    name = 'Aramex'

    _code_to_description = {
        'PDX': 'Priority document express',
        'PPX': 'Priority parcel express',
        'PLX': 'Priority letter express',
        'DDX': 'Deferred document express',
        'DPX': 'Deferred parcel express',
        'GDX': 'Ground document express',
        'GPX': 'Ground parcel express',
        'EPX': 'Economy Parcel Express',
        'OND': 'OND'
    }

    _product_group_to_description = {
        'EXP': 'International shipment',
        'DOM': 'Domestic shipment'
    }

    _service_code_to_description = {
        'COD': 'Cash on delivery',
        'FIRST': 'First delivery',
        'FRDOM': 'Free domicile',
        'HFPU': 'Hold for pickup',
        'NOON': 'Noon delivery',
        'SIG': 'Signature required'
    }

    _min_max_estimates = {
        'PDX': (7, 10),
        'PPX': (7, 10),
        'PLX': (7, 10),
        'DDX': (7, 10),
        'DPX': (7, 10),
        'GDX': (7, 10),
        'GPX': (7, 10)
    }

    _carrier_error_codes = {
         'ERR61': 'Failed to get rates',
         'ERR52': 'Service not available'
    }

    _translatable_errors = {
        'ERR06': (
            AddressError, 'Please double-check the postal code.',
            {'fields': {'postal_code': 'Please double-check the postal code.'}}
        ),
        'ERR52-b': (
            AddressError,
            'Please double-check the city name to get rates for Aramex.',
            {'fields': {'city': 'Please double-check the city.'}}
        )
    }

    _switchable_messages = {
        'City name is invalid': 'ERR52-b'
    }

    _rate_client = None
    _priority_letter_limit = 1.10231
    carrier_error = None
    _ship_client = None
    _track_client = None

    def create_client(self, wsdl_name):
        client = Client(
            self.service_url(wsdl_name), plugins=[ClearEmpty(), self.log_service],
            timeout=self.postal_configuration.get('timeout', None))

        return client

    def __init__(
            self, account_country_code, account_entity,
            account_number, account_pin, username,
            password, test, postal_configuration=None
    ):
        super(AramexApi, self).__init__(postal_configuration)
        self.postal_configuration = postal_configuration
        self.account_country_code = account_country_code
        self.account_entity = account_entity
        self.account_number = account_number
        self.account_pin = account_pin
        self.username = username
        self.password = password
        self.version = 1
        self.test = True

    @property
    def rates_client(self):
        if not self._rate_client:
            self._rate_client = self.create_client('rates.wsdl')
        return self._rate_client

    @property
    def ship_client(self):
        if not self._ship_client:
            self._ship_client = self.create_client('shipping.wsdl')
        return self._ship_client

    @property
    def track_client(self):
        if not self._track_client:
            self._track_client = self.create_client('tracking.wsdl')
        return self._track_client

    def requested_shipment_details(self, request):
        api_request = self.rates_client.factory.create('RateCalculatorRequest')
        api_request.ClientInfo = self.client_info
        if not request.origin:
            request.origin = self.postal_configuration['shipper_address']
        self.set_address(api_request.OriginAddress, request.origin)
        self.set_address(api_request.DestinationAddress, request.destination)
        self.set_shipment_details(api_request.ShipmentDetails, request)
        return api_request

    @classmethod
    def set_address(cls, target, postal_address):
        target.City = postal_address.city
        target.CountryCode = postal_address.country.alpha2
        target.PostCode = postal_address.postal_code
        lines = cls.break_line(postal_address.street_lines)
        target.StateOrProvinceCode = postal_address.subdivision
        for line, value in lines.items():
            setattr(target, line, value)

    def set_shipment_details(self, target, request):
        target.Dimensions = None
        target.ProductGroup = 'DOM'
        if request.international():
            target.ProductGroup = 'EXP'
        target.ActualWeight.Unit = 'LB'
        target.ActualWeight.Value = request.total_weight()
        target.ChargeableWeight = target.ActualWeight
        target.PaymentType = 'P'
        target.NumberOfPieces = len(request.packages)

    def shipment_request_details(self, request_info):
        request, service = request_info
        api_request = self.ship_client.factory.create('ShipmentCreationRequest')
        api_request.ClientInfo = self.client_info
        api_request.LabelInfo = self.label_info()
        if not request.origin:
            request.origin = self.postal_configuration['shipper_address']
        api_request.Shipments.Shipment = self.set_shipper_details(request_info)
        return api_request

    def set_shipper_details(self, request_info):
        request, service = request_info
        target = self.ship_client.factory.create('Shipment')
        # set shipper address
        shipper = request.origin
        target.Shipper.AccountNumber = self.account_number
        lines = self.break_line(shipper.street_lines)
        for line, value in lines.items():
            setattr(target.Shipper.PartyAddress, line, value)

        target.Shipper.PartyAddress.City = shipper.city
        target.Shipper.PartyAddress.PostCode = shipper.postal_code
        target.Shipper.PartyAddress.CountryCode = shipper.country.alpha2

        target.Shipper.Contact.PersonName = shipper.contact_name
        target.Shipper.Contact.PhoneNumber1 = shipper.phone_number
        target.Shipper.Contact.PhoneNumber2 = ''
        target.Shipper.Contact.CellPhone = shipper.phone_number
        shipper_email = 'support@usglobalmail.com'
        if shipper.email:
            shipper_email = shipper.email
        target.Shipper.Contact.EmailAddress = shipper_email

        target.Shipper.Contact.Type = 1

        # set consignee details
        consignee = request.destination
        lines = self.break_line(consignee.street_lines)

        for line, value in lines.items():
            setattr(target.Consignee.PartyAddress, line, value)

        target.Consignee.PartyAddress.City = consignee.city
        target.Consignee.PartyAddress.PostCode = consignee.postal_code
        target.Consignee.PartyAddress.CountryCode = consignee.country.alpha2
        target.Consignee.Contact.PersonName = consignee.contact_name
        target.Consignee.Contact.CompanyName = 'NA'
        target.Consignee.Contact.PhoneNumber1 = consignee.phone_number
        target.Consignee.Contact.PhoneNumber2 = ''
        target.Consignee.Contact.CellPhone = consignee.phone_number

        # Consignee email address is mandatory, any string can be set
        consignee_email = consignee.contact_name
        if consignee.email:
            consignee_email = consignee.email
        target.Consignee.Contact.EmailAddress = consignee_email
        target.Consignee.Contact.Type = 1
        target.ShippingDateTime = datetime.now()
        target.DueDate = datetime.now()

        # Attach commercial invoice
        attachment = self.ship_client.factory.create('Attachment')
        attachment.FileName = 'commercial_invoice'
        attachment.FileExtension = 'pdf'
        attachment.FileContents = self.commercial_invoice(request)
        target.Attachments = attachment

        items = []
        insurance_amount = 0
        container_number = 1
        for package in request.packages:
            container_number += 1
            target.Details.Dimensions.Length = Decimal(Package.to_centimeters(package.length)).quantize(TWOPLACES)
            target.Details.Dimensions.Width = Decimal(Package.to_centimeters(package.width)).quantize(TWOPLACES)
            target.Details.Dimensions.Height = Decimal(Package.to_centimeters(package.height)).quantize(TWOPLACES)
            target.Details.Dimensions.Unit = 'CM'
            if package.declarations:
                declarations = package.declarations[:]
                for declaration in declarations:
                    shipment_item = self.ship_client.factory.create('ShipmentItem')
                    shipment_item.PackageType = ''
                    shipment_item.Quantity = declaration.units
                    shipment_item.Weight = package.weight
                    shipment_item.GoodsDescription = declaration.description
                    shipment_item.CustomsValue.CurrencyCode = declaration.value.currency
                    shipment_item.CustomsValue.Value = declaration.value.amount
                    shipment_item.ContainerNumber = container_number
                    shipment_items_copy = deepcopy(shipment_item)
                    items.append(shipment_items_copy)
                value = package.get_total_insured_value()
                if value > 0:
                    insurance_amount = insurance_amount + value.amount
        if insurance_amount > 0:
            target.Details.InsuranceAmount.CurrencyCode = self.postal_configuration['default_currency']
            target.Details.InsuranceAmount.Value = insurance_amount
        target.Details.Items = items

        target.Details.ActualWeight.Value = request.total_weight()
        target.Details.ActualWeight.Unit = 'LB'
        target.Details.ChargeableWeight.Unit = 'LB'
        target.Details.ChargeableWeight.Value = 1
        target.Details.ProductGroup = 'DOM'
        if request.international():
            target.Details.ProductGroup = 'EXP'
        target.Details.ProductType = service.service_id
        target.Details.PaymentType = 'P'
        target.Details.NumberOfPieces = len(request.packages)
        target.Details.GoodsOriginCountry = shipper.country.alpha2
        target.Details.PaymentOptions = ''
        target.Details.CustomsValueAmount.CurrencyCode = self.postal_configuration['default_currency']
        target.Details.CustomsValueAmount.Value = 1
        return target

    @staticmethod
    def break_line(street_lines):
        return {
            'Line{}'.format(num + 1): line
            for num, line in enumerate(street_lines)
        }

    @property
    def client_info(self, ship=False):
        if ship:
            client = self.ship_client.factory.create('ClientInfo')
        else:
            client = self.rates_client.factory.create('ClientInfo')
        client.UserName = self.username
        client.Password = self.password
        client.Version = self.version
        if self.account_number:
            client.AccountNumber = self.account_number
            client.AccountEntity = self.account_entity
            client.AccountPin = self.account_pin
            client.AccountCountryCode = self.account_country_code
        return client

    def label_info(self):
        label = self.ship_client.factory.create('LabelInfo')
        label.ReportID = '9201'
        label.ReportType = 'RPT'
        return label

    def service_call(self, func, *args, **kwargs):
        response = super(AramexApi, self).service_call(func, *args, **kwargs)
        if response.HasErrors:
            msg = ''
            for notification in response.Notifications.Notification:
                code = notification['Code']
                message = notification['Message']
                # Handle the nightmare that is Aramex error handling.
                # They use the same code for multiple things.
                for key in self._switchable_messages:
                    if key in message:
                        code = self._switchable_messages[key]
                        break
                if code in self._translatable_errors:
                    cls, msg, kwargs = self._translatable_errors[code]
                    raise cls(msg, code=code, **kwargs)
                msg += '{} {}.'.format(code, message)
                raise CarrierError(
                    msg, code=code
                )
        return response

    def get_services(self, request, service=False):
        AramexApi.carrier_error = None
        return self.process_request((request, False), service=service)

    def track(self, identifier):
        client_info = self.client_info
        transaction = self.track_client.factory.create('Transaction')
        tracking_numbers = self.track_client.factory.create('ns1:ArrayOfstring')
        tracking_numbers.string.append(identifier)
        try:
            self.track_client.service.TrackShipments(client_info, transaction, tracking_numbers, True)
        except TypeNotFound:
            # We expect this to always happen because of a bug in Aramex's wsdl. We will still have access to the
            # raw XML, so we'll handle it here.
            pass
        response = self.log_service.last_received_reply
        it = iterparse(StringIO(response))
        for _, el in it:
            if '}' in el.tag:
                el.tag = el.tag.split('}', 1)[1]  # strip all namespaces
        response = it.root
        result = response.find('Body').find(
            'ShipmentTrackingResponse').find('TrackingResults').find(
                'KeyValueOfstringArrayOfTrackingResultmFAkxlpY'
        ).find(
            'Value'
        ).find('TrackingResult')
        event_code = result.findtext('UpdateCode')
        city, country = result.findtext('UpdateLocation').split(', ')
        country = country.lower()

        return {
            'delivered': event_code == 'SH001',
            'finalized': event_code in ['SH001'],
            'status_code': u'{}'.format(event_code),
            'description': u'{}'.format(result.findtext('UpdateDescription')),
            'event_time': parser.parse(result.findtext('UpdateDateTime')),
            'location': Address(street_lines=[' '], city=city, country=country_map.get(country).alpha2)
        }

    def ship(self, service, request):
        AramexApi.carrier_error = None
        return self.process_request((request, True), service=service)

    def process_request(self, request_info, service):
        AramexApi.carrier_error = None
        request, ship = request_info
        requests = self.get_requests((request, ship), service=service)
        thread_pool = ThreadPool(processes=len(requests))
        results = thread_pool.map(self.get_request_rate, [(api_request, ship, service) for api_request in requests])
        thread_pool.terminate()
        thread_pool.join()
        if AramexApi.carrier_error:
            if ship:
                raise AramexApi.carrier_error
        if ship:
            result = results[0]
            tracking_number = str(result.Shipments.ProcessedShipment[0].ID)
            package = request.packages[0]
            package_details = OrderedDict()
            package_details[package] = {
                'tracking_number': str(tracking_number),
                'label': self.format_label(result.Shipments.ProcessedShipment[0].ShipmentLabel.LabelFileContents)
            }
            shipment_dict = {
                'shipment': Shipment(self, tracking_number),
                'packages': package_details,
                'price': self.quote(service, request),
            }
            with logger.lock:
                logger.debug_header('Response')
                logger.shipment_response(shipment_dict)
            return shipment_dict

        final = {
            self.get_service(key): {
                'price': value,
                'delivery_datetime': None,
                'trackable': True
            } for response in results if response and not response['error'] for key, value in response['service'].items()
        }
        with logger.lock:
            logger.debug_header('Response')
            logger.debug(pformat(final, width=1))

        if final:
            return final
        codes = [response['error'] for response in results if response['error'].code not in self._carrier_error_codes]
        if codes:
            raise codes[0]
        return {}

    def get_request_rate(self, request_info):
        request, ship, service = request_info
        try:
            if ship:
                return self.service_call(
                    self.ship_client.service.CreateShipments, request.ClientInfo, request.Transaction,
                    request.Shipments, request.LabelInfo
                )
            else:
                response = self.service_call(
                    self.rates_client.service.CalculateRate, request.ClientInfo, request.Transaction,
                    request.OriginAddress, request.DestinationAddress, request.ShipmentDetails
                )
                return {'service': {request.ShipmentDetails.ProductType: self.get_price_dict(response)}, 'error': None}
        except CarrierError as e:
            return {'service': {request.ShipmentDetails.ProductType:{}}, 'error': e}

    def get_price_dict(self, info):
        price = {}
        price['base_price'] = Money(info.TotalAmount.Value, info.TotalAmount.CurrencyCode)
        price['total'] = price['base_price']
        price['fees'] = Money(0, info.TotalAmount.CurrencyCode)
        return price

    def get_requests(self, request_info, service):
        request, ship = request_info
        requests = []
        if ship:
            api_request = self.shipment_request_details((request, service))
            requests.append(api_request)
            return requests
        flat_services = ['PDX', 'PLX', 'DDX', 'GDX']
        non_flat_services = ['PPX', 'DPX', 'GPX', 'EPX']
        api_request = self.requested_shipment_details(request)
        if service:
            api_req = deepcopy(api_request)
            api_req.ShipmentDetails.ProductType = service.service_id
            requests.append(api_req)
            return requests
        if request.documents_only():
            if request.total_weight() < self._priority_letter_limit and not request.international():
                api_req = deepcopy(api_request)
                api_req.ShipmentDetails.ProductType = 'OND'
                requests.append(api_req)
            for service in flat_services:
                api_req = deepcopy(api_request)
                api_req.ShipmentDetails.ProductType = service
                requests.append(api_req)
        for service in non_flat_services:
            api_req = deepcopy(api_request)
            api_req.ShipmentDetails.ProductType = service
            requests.append(api_req)
        return requests

    def quote(self, service, request):
        data = self.get_services(request, service=service)
        return data[service]['price']

    @staticmethod
    def format_label_old(label):
        import requests
        r = requests.get(label, stream=True)
        return r.content

    @staticmethod
    def format_label(label):
        # Some jump-around for dual compatibility with Python 2 and 3
        if isinstance(label, bytes):
            label = label.decode('utf-8')
        label = b64decode(label)
        input = PdfFileReader(BytesIO(label))
        input.strict = False
        output = PdfFileWriter()
        page = input.getPage(0)
        output.addPage(page)
        output_stream = BytesIO()
        output.write(output_stream)
        return output_stream.getvalue()
