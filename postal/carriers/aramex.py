from multiprocessing.pool import ThreadPool

from suds.client import Client
from money import Money
from postal.carriers.base import Carrier, ClearEmpty
from postal.exceptions import CarrierError
from datetime import datetime, date
from postal.data import Package
from io import BytesIO
from base64 import b64decode
from ..exceptions import PostalError
from PyPDF2 import PdfFileReader, PdfFileWriter
from copy import deepcopy
from .base import Carrier
from ..data import Address, Shipment, Declaration
from collections import OrderedDict
from decimal import Decimal

TWOPLACES = Decimal('0.01')
class AramexApi(Carrier):
    """
    Implements calls to the aramex api.
    """
    name = 'Aramex'

    _code_to_description = {
        'PDX' : 'Priority document express',
        'PPX': 'Priority parcel express',
        'PLX': 'Priority letter express',
        'DDX': 'Deferred document express',
        'DPX' : 'Deferred parcel express',
        'GDX': 'Ground document express',
        'GPX': 'Ground parcel express',
        'OND': 'OND'
    }

    _product_group_to_description = {
        'EXP' : 'International shipment',
        'DOM' : 'Domestic shipment'
    }

    _service_code_to_description = {
        'COD' : 'Cash on delivery',
        'FIRST' : 'First delivery',
        'FRDOM' : 'Free domicile',
        'HFPU' : 'Hold for pickup',
        'NOON': 'Noon delivery',
        'SIG' : 'Signature required'
    }

    _min_max_estimates = {
        'PDX' : (1, 2),
        'PPX': (1, 2),
        'PLX': (1, 2),
        'DDX': (1, 2),
        'DPX' : (1, 2),
        'GDX': (1, 3),
        'GPX': (1, 3)
    }

    _carrier_error_codes = {
         'ERR61' : 'Failed to get rates',
         'ERR52' : 'Service not available'
    }

    _rate_client = None
    _priority_letter_limit = 1.10231
    carrier_error = None
    _ship_client = None


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
            self._ship_client = self.create_client('shipping-services-api-wsdl.wsdl')
        return self._ship_client

    def requested_shipment_details(self, request):
        api_request = self.rates_client.factory.create('RateCalculatorRequest')
        api_request.ClientInfo = self.client_info
        if not request.origin:
            request.origin = self.postal_configuration['shipper_address']
        self.set_address(api_request.OriginAddress, request.origin)
        self.set_address(api_request.DestinationAddress, request.destination)
        self.set_shipment_details(api_request.ShipmentDetails, request)
        return api_request

    @staticmethod
    def set_address(target, postal_address):
        target.City = postal_address.city
        target.CountryCode = postal_address.country.alpha2
        target.PostCode = postal_address.postal_code
        lines = {
            'Line{}'.format(num + 1) : line
                for num, line in enumerate(postal_address.street_lines)
        }
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

    def set_shipment_items (self, target, request):
        for package in request.packages:
            shipment_item = self.rates_client.factory.create('ShipmentItem')
            shipment_item.PackageType = 'DDX'
            shipment_item.Quantity = 1
            shipment_item.Weight = package.weight
            shipment_item.Comments = ''
            target.append(shipment_item)

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
        lines = {
            'Line{}'.format(num + 1) : line
                for num, line in enumerate(shipper.street_lines)
        }
        for line, value in lines.items():
            setattr(target.Shipper.PartyAddress, line, value)

        target.Shipper.PartyAddress.City = shipper.city
        target.Shipper.PartyAddress.PostCode = shipper.postal_code
        target.Shipper.PartyAddress.CountryCode = shipper.country.alpha2

        target.Shipper.Contact.PersonName = shipper.contact_name
        target.Shipper.Contact.PhoneNumber1 = shipper.phone_number
        target.Shipper.Contact.PhoneNumber2 = ''
        target.Shipper.Contact.CellPhone = shipper.phone_number
        target.Shipper.Contact.EmailAddress = request.extra_params['admin'].email
        target.Shipper.Contact.Type = 1

        # set consignee details
        consignee = request.destination
        lines = {
            'Line{}'.format(num + 1) : line
                for num, line in enumerate(consignee.street_lines)
        }
        for line, value in lines.items():
            setattr(target.Consignee.PartyAddress, line, value)

        target.Consignee.PartyAddress.City = ''
        target.Consignee.PartyAddress.PostCode = consignee.postal_code
        target.Consignee.PartyAddress.CountryCode = consignee.country.alpha2
        target.Consignee.Contact.PersonName = consignee.contact_name
        target.Consignee.Contact.CompanyName = 'NA'
        target.Consignee.Contact.PhoneNumber1 = consignee.phone_number
        target.Consignee.Contact.PhoneNumber2 = ''
        target.Consignee.Contact.CellPhone = consignee.phone_number
        target.Consignee.Contact.EmailAddress = request.extra_params['customer'].email
        target.Consignee.Contact.Type = 1

        target.ShippingDateTime = datetime.now()
        target.DueDate = datetime.now()

        # Attach commercial invoice
        attachment = self.ship_client.factory.create('Attachment')
        attachment.FileName = 'commercial_invoice'
        attachment.FileExtension = 'pdf'
        attachment.FileContents = self.commercial_invoice(request)
        target.Attachments = attachment

        description = ''
        items = []
        for package in request.packages:
            target.Details.Dimensions.Length = Decimal(Package.to_centimeters(package.length)).quantize(TWOPLACES)
            target.Details.Dimensions.Width = Decimal(Package.to_centimeters(package.width)).quantize(TWOPLACES)
            target.Details.Dimensions.Height = Decimal(Package.to_centimeters(package.height)).quantize(TWOPLACES)
            target.Details.Dimensions.Unit = 'CM'

            shipment_item = self.ship_client.factory.create('ShipmentItem')
            shipment_item.PackageType = ''
            shipment_item.Quantity = 1
            shipment_item.Weight = package.weight
            shipment_item.Comments = ''
            items.append(shipment_item)

            declarations = package.declarations[:]
            for declaration in declarations:
                description += declaration.description + ', '

        target.Details.DescriptionOfGoods = description
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
        target.Details.CustomsValueAmount.CurrencyCode = 'USD'
        target.Details.CustomsValueAmount.Value = 1
        return target

    @property
    def client_info(self,ship=False):
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
        label.ReportType = 'URL'
        return label

    def service_call(self, func, *args, **kwargs):
        response = super(AramexApi, self).service_call(func, *args, **kwargs)
        if response.HasErrors:
            msg = ''
            for notification in response.Notifications.Notification:
                msg += '{} '.format(notification['Code']) + str(notification['Message']) + '.'
                raise CarrierError(msg, code=notification['Code'])

        return response

    def get_services(self, request, service=False):
        AramexApi.carrier_error = None
        return self.process_request((request, False), service=service)

    def ship(self, service, request):
        AramexApi.carrier_error = None
        return self.process_request((request, True), service=service)

    def process_request(self, request_info, service):
        AramexApi.carrier_error = None
        request, ship = request_info
        requests= self.get_requests((request, ship), service=service)
        thread_pool = ThreadPool(processes=len(requests))
        results = thread_pool.map(self.get_request_rate, [(api_request, ship, service)   for api_request in requests])
        thread_pool.terminate()
        thread_pool.join()
        if AramexApi.carrier_error:
            raise AramexApi.carrier_error

        if ship:
            result = results[0]
            tracking_number = str(result.Shipments.ProcessedShipment[0].ID)
            package = request.packages[0]
            package_details = OrderedDict()
            package_details[package] = {
                'tracking_number': str(tracking_number),
                'label': self.format_label(result.Shipments.ProcessedShipment[0].ShipmentLabel.LabelURL)
            }
            shipment_dict = {
                'shipment': Shipment(self, tracking_number),
                'packages': package_details,
                'price': self.quote(request, service),
            }
            return shipment_dict

        else:
            final = {
                self.get_service(key): {
                    'price': value,
                    'delivery_datetime': None,
                    'trackable': True
                } for response in results if response for key, value in response.items()
            }
            return final

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
                return { request.ShipmentDetails.ProductType: self.get_price_dict(response)}
        except CarrierError as e:
            if e.code not in self._carrier_error_codes:
                # These error codes mean that the product type is not available for this particular request
                # so we just ignore it.
                AramexApi.carrier_error = e
            return None

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
        else:
            flat_services = ['PDX', 'PLX', 'DDX', 'GDX']
            non_flat_services = ['PPX', 'DPX', 'GPX']
            api_request = self.requested_shipment_details(request)
            if service:
                api_req = deepcopy(api_request)
                api_req.ShipmentDetails.ProductType = service.service_id
                requests.append(api_req)
            else:
                if request.documents_only:
                    if request.total_weight() < self._priority_letter_limit:
                        if not request.international():
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

    def quote(self, request, service):
        data = self.get_services(request, service=service)
        return data[service]['price']

    @staticmethod
    def format_label(label):
        import requests
        r = requests.get(label, stream=True)
        return r.content


