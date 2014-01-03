"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import os
from base64 import b64decode
from datetime import datetime
from math import ceil
from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from suds.client import Client
from money import Money

from base import Carrier, Service, ClearEmpty
from ..exceptions import CarrierError, NotSupportedError
from ..data import Address, Shipment


class FedExApi(Carrier):
    """
    Implements calls to the FedEx web API.
    """
    name = 'FedEx'
    address_validation = True
    _code_to_description = {
        'FIRST_OVERNIGHT': 'First Overnight',
        'PRIORITY_OVERNIGHT': 'Priority Overnight',
        'STANDARD_OVERNIGHT': 'Standard Overnight',
        'FEDEX_2_DAY': '2-Day',
        'FEDEX_2_DAY_AM': '2-Day AM Delivery',
        'FEDEX_EXPRESS_SAVER': 'Express Saver',
        'FEDEX_GROUND': 'Ground',
        'FEDEX_HOME_DELIVERY': 'Home Delivery',
        'SMART_POST': 'SmartPost',
        'GROUND_HOME_DELIVERY': 'Ground Home Delivery',
        'SAME_DAY': 'Same Day',
        'SAME_DAY_CITY': 'Same Day City',
        'FEDEX_FREIGHT_ECONOMY': 'Freight Economy',
        'FEDEX_FREIGHT_PRIORITY': 'Freight Priority',
        'FEDEX_FIRST_FREIGHT': 'First Freight',
        'FEDEX_3_DAY_FREIGHT': '3-Day Freight',
        'INTERNATIONAL_ECONOMY': 'International Economy',
        'INTERNATIONAL_ECONOMY_FREIGHT': 'International Economy Freight',
        'INTERNATIONAL_FIRST': 'International First',
        'INTERNATIONAL_PRIORITY': 'International Priority',
        'EUROPE_FIRST_INTERNATIONAL_PRIORITY': 'Europe First '
                                               'International Priority'}

    @staticmethod
    def service_url(wsdl_name):
        base_path = os.path.split(os.path.abspath(
            inspect.getfile(inspect.currentframe())))[0]
        base_path = os.path.join(base_path, 'wsdl', 'fedex')
        full_path = os.path.join(base_path, wsdl_name)
        return "file://%s" % full_path

    def create_client(self, wsdl_name):
        return Client(
            self.service_url(wsdl_name), plugins=[ClearEmpty()],
            timeout=self.postal_configuration['timeout'])

    def __init__(
            self, key, account_number, password, meter_number,
            postal_configuration=None):
        super(FedExApi, self).__init__(postal_configuration)
        self.postal_configuration = postal_configuration
        self.key = key
        self.account_number = account_number
        self.password = password
        self.meter_number = meter_number

        self.rates_client = self.create_client('RateService_v14.wsdl')

        self.address_client = self.create_client(
            'AddressValidationService_v2.wsdl')

        self.ship_client = self.create_client('ShipService_v13.wsdl')

        self.contact_type = (
            self.rates_client.factory.create('Party').__class__)

    def authentication(self, client):
        auth = client.factory.create('WebAuthenticationDetail')
        keys = client.factory.create('WebAuthenticationCredential')
        keys.Key = self.key
        keys.Password = self.password
        auth.UserCredential = keys
        return auth

    def service_call(self, func, *args, **kwargs):
        response = super(FedExApi, self).service_call(func, *args, **kwargs)
        if response.HighestSeverity in ["FAILURE", "ERROR"]:
            raise CarrierError(response.Notifications[0].Message)
        return response

    def user_client(self, client):
        client_detail = client.factory.create('ClientDetail')
        client_detail.AccountNumber = self.account_number
        client_detail.MeterNumber = self.meter_number
        client_detail.Localization.LanguageCode = 'EN'
        client_detail.Localization.LocaleCode = 'us'
        return client_detail

    def transaction_detail(self, client):
        return client.factory.create('TransactionDetail')

    def address_validation_options(self):
        options = self.address_client.factory.create(
            'AddressValidationOptions')
        options.VerifyAddresses = True
        options.CheckResidentialStatus = True
        options.RecognizeAlternateCityNames = True
        return options

    def address_version_id(self):
        version = self.address_client.factory.create('VersionId')
        version.ServiceId = 'aval'
        version.Major = 2
        version.Intermediate = 0
        version.Minor = 0
        return version

    def address_from_validator(self, result, original):
        residential = result.ResidentialStatus == "RESIDENTIAL"
        addr = result.Address
        return Address(
            contact_name=original.contact_name,
            street_lines=list(addr.StreetLines),
            city=addr.City,
            subdivision=addr.StateOrProvinceCode,
            postal_code=addr.PostalCode,
            country=addr.CountryCode,
            residential=residential,
            phone_number=original.phone_number)

    def validate_address(self, address):
        auth = self.authentication(self.address_client)
        client_detail = self.user_client(self.address_client)
        transaction_detail = self.transaction_detail(self.address_client)
        version_id = self.address_version_id()
        request_timestamp = datetime.now()
        address_validation_options = self.address_validation_options()
        address_item = self.address_client.factory.create('AddressToValidate')
        self.set_address(address_item, address)
        result = self.service_call(
            self.address_client.service.addressValidation,
            auth, client_detail, transaction_detail, version_id,
            request_timestamp, address_validation_options, address_item)
        result = result.AddressResults[0][0][0]
        success = result.Score
        address = self.address_from_validator(result, address)
        return success, address

    def ship_version_id(self):
        version = self.ship_client.factory.create('VersionId')
        version.ServiceId = 'ship'
        version.Major = 13
        version.Intermediate = 0
        version.Minor = 0
        return version

    def rates_version_id(self):
        version = self.rates_client.factory.create('VersionId')
        version.ServiceId = 'crs'
        version.Major = 14
        version.Intermediate = 0
        version.Minor = 0
        return version

    def label_specification(self, spec):
        spec.LabelFormatType = 'COMMON2D'
        spec.ImageType = 'PDF'
        spec.LabelStockType = 'PAPER_4X6'

    @staticmethod
    def format_label(label):
        input = PdfFileReader(StringIO(b64decode(label)))
        output = PdfFileWriter()

        page = input.getPage(0)
        page.mediaBox.lowerLeft = (30, 325)
        page.mediaBox.upperRight = (320, 760)
        output.addPage(page)
        output_stream = StringIO()
        output.write(output_stream)
        return output_stream.getvalue()

    def requested_shipment(
            self, service, request, package, sequence_num=None,
            tracking_number=None):
        """
        FedEx supports Multiship, but only one package at a time. They have to
        be 'added' to the initial request with secondary requests.
        """
        origin = request.origin or self.postal_configuration['shipper_address']

        api_request = self.ship_client.factory.create('RequestedShipment')
        api_request.ShipTimestamp = request.ship_datetime or datetime.now()
        api_request.ServiceType = service.service_id
        api_request.DropoffType = 'REGULAR_PICKUP'
        if package.document:
            api_request.PackagingType = 'FEDEX_ENVELOPE'
        else:
            api_request.PackagingType = 'YOUR_PACKAGING'
        api_request.RateRequestTypes = 'ACCOUNT'
        self.set_address(api_request.Shipper, origin)
        self.set_address(api_request.Recipient, request.destination)
        payment = api_request.ShippingChargesPayment
        payment.PaymentType = 'SENDER'
        party = payment.Payor.ResponsibleParty
        party.AccountNumber = self.account_number
        party.Contact.PersonName = origin.contact_name
        party.Contact.PhoneNumber = origin.phone_number
        self.label_specification(api_request.LabelSpecification)
        if tracking_number:
            api_request.MasterTrackingId = tracking_number
        if not tracking_number:
            api_request.TotalWeight.Value = sum(
                [int(ceil(pack.weight)) for pack in request.packages])
            api_request.TotalWeight.Units = 'LB'
        api_request.PackageCount = len(request.packages)
        self.line_items(
            self.ship_client, api_request, request, [package], sequence_num)
        return api_request

    def ship(self, service, request):
        auth = self.authentication(self.ship_client)
        client_detail = self.user_client(self.ship_client)
        transaction_detail = self.transaction_detail(self.ship_client)
        version_id = self.ship_version_id()
        package = request.packages[0]
        requested_shipment = self.requested_shipment(service, request, package)
        result = self.service_call(
            self.ship_client.service.processShipment, auth, client_detail,
            transaction_detail, version_id, requested_shipment)
        package_details = {}
        if len(request.packages) > 1:
            master_tracking_id = (
                result.CompletedShipmentDetail.MasterTrackingId)
        else:
            master_tracking_id = (
                result.CompletedShipmentDetail.CompletedPackageDetails[
                    0].TrackingIds[0])
        detail = result.CompletedShipmentDetail.CompletedPackageDetails[0]
        package_details[package] = {
            'tracking_number': master_tracking_id.TrackingNumber,
            'label': self.format_label(detail.Label.Parts[0].Image)}
        for sequence_num, package in enumerate(request.packages[1:]):
            sequence_num += 2
            requested_shipment = self.requested_shipment(
                service, request, package, sequence_num=sequence_num,
                tracking_number=master_tracking_id)
            result = self.service_call(
                self.ship_client.service.processShipment, auth, client_detail,
                transaction_detail, version_id, requested_shipment)
            detail = result.CompletedShipmentDetail.CompletedPackageDetails[0]
            package_details[package] = {
                'tracking_number': (
                    detail.TrackingIds[0].TrackingNumber),
                'label': self.format_label(detail.Label.Parts[0].Image)}
        tracking_number = master_tracking_id.TrackingNumber

        try:
            rating = result.CompletedShipmentDetail.ShipmentRating
            price = self.get_real_price(rating, rating.ShipmentRateDetails)
        except (CarrierError, AttributeError):
            raise CarrierError("FedEx returned a nonsense price. Please "
                               "contact their customer service about tracking "
                               "number %s." % tracking_number)
        shipment_dict = {
            'shipment': Shipment(self, tracking_number),
            'packages': package_details,
            'price': price}
        return shipment_dict

    def carrier_codes(self):
        codes = self.rates_client.factory.create('CarrierCodeType')
        return [codes.FDXE, codes.FDXG]

    def line_items(
            self, client, api_request, request, packages, sequence_num=None):
        for index, package in enumerate(packages):
            item = client.factory.create('RequestedPackageLineItem')
            item.SequenceNumber = sequence_num or index + 1
            item.GroupNumber = 1
            item.GroupPackageCount = 1
            item.Weight.Units.value = 'LB'
            item.Weight.Value = int(ceil(package.weight))

            dimensions = item.Dimensions
            dimensions.Height = int(ceil(package.height))
            dimensions.Width = int(ceil(package.width))
            dimensions.Length = int(ceil(package.length))
            dimensions.Units = 'IN'

            if package.declarations:
                self.set_declarations(client, api_request, package)

                value = package.get_total_insured_value()
                if value > 0:
                    item.InsuredValue.Currency = value.currency
                    item.InsuredValue.Amount = value.amount

            api_request.RequestedPackageLineItems.append(item)
        if api_request.CustomsClearanceDetail.Commodities:
            detail = api_request.CustomsClearanceDetail
            detail.DutiesPayment.PaymentType = 'RECIPIENT'

    @staticmethod
    def set_address(target, address):
        target_address = target.Address
        if hasattr(target, 'Contact'):
            target.Contact.PersonName = address.contact_name
            target.Contact.PhoneNumber = address.phone_number
        target_address.StreetLines = address.street_lines
        target_address.City = address.city
        target_address.PostalCode = address.postal_code
        target_address.CountryCode = address.country.alpha2
        target_address.StateOrProvinceCode = address.subdivision
        target_address.Residential = address.residential

    def set_declarations(self, client, api_request, package):
        commodities = []
        total_value = 0
        for declaration in package.declarations:
            commodity = client.factory.create('Commodity')
            commodity.Description = declaration.description
            value = declaration.value
            commodity.NumberOfPieces = declaration.units
            commodity.UnitPrice.Currency = value.currency
            commodity.UnitPrice.Amount = value.amount
            value = value * declaration.units
            commodity.CountryOfManufacture = declaration.origin_country.alpha2
            commodity.CustomsValue.Currency = value.currency
            commodity.CustomsValue.Amount = value.amount
            commodity.Weight.Value = 0
            commodity.Weight.Units = 'LB'
            commodity.QuantityUnits = 'EA'
            commodity.Quantity = declaration.units
            commodities.append(commodity)
            total_value += value
        api_request.CustomsClearanceDetail.Commodities.extend(commodities)
        value = api_request.CustomsClearanceDetail.CustomsValue
        if value.Amount is None:
            value.Amount = 0
        value.Amount += total_value.amount
        value.Currency = total_value.currency

    def requested_shipment_rate(self, request):
        api_request = self.rates_client.factory.create('RequestedShipment')

        origin = request.origin or self.postal_configuration['shipper_address']
        self.set_address(api_request.Shipper, origin)
        self.set_address(api_request.Recipient, request.destination)

        api_request.RateRequestTypes = 'ACCOUNT'
        api_request.PackageCount = len(request.packages)

        self.line_items(
            self.rates_client, api_request, request, request.packages)
        api_request.ShipTimestamp = request.ship_datetime

        return api_request

    @staticmethod
    def get_real_price(info, method_details):
        try:
            actual_type = info.ActualRateType
        except AttributeError as err:
            raise err
        price = None
        for rating in method_details:
            try:
                rating = rating.ShipmentRateDetail
            except AttributeError:
                pass
            if actual_type == rating.RateType:
                price = Money(
                    rating.TotalNetCharge.Amount,
                    rating.TotalNetCharge.Currency)
        if not price:
            raise CarrierError("FedEx returned a nonsense price.")
        return price

    @staticmethod
    def rate_response_dict(response):
        if not hasattr(response, 'RateReplyDetails'):
            return {}
        return {
            method.ServiceType: {
                #'service': method.ServiceType,
                'price': FedExApi.get_real_price(
                    method, method.RatedShipmentDetails),
                'delivery_datetime': getattr(
                    method, 'DeliveryTimestamp', None)}
            for method in response.RateReplyDetails}

    def create_service(self, service):
        return Service(
            self, service, self._code_to_description[service])

    def get_services(self, request):
        """
        Get available services for shipping a package.
        """
        auth = self.authentication(self.rates_client)
        client = self.user_client(self.rates_client)
        transaction_detail = self.transaction_detail(self.rates_client)
        version = self.rates_version_id()
        return_transit = True
        codes = []
        variable_options = []
        requested_shipment = self.requested_shipment_rate(request)
        response = self.service_call(
            self.rates_client.service.getRates,
            auth, client, transaction_detail, version, return_transit, codes,
            variable_options, requested_shipment)
        result = self.rate_response_dict(response)
        self.cache_results(request, result)

        final = {
            self.create_service(key): {
                'price': value['price'],
                'delivery_datetime': value['delivery_datetime']}
            for key, value in result.items()}

        return final

    def delivery_datetime(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[tuple(request)].get(service.service_id, None)
        if not data:
            raise NotSupportedError(
                "FedEx does not support shipment of that package(s).")
        return data['delivery_datetime']

    def quote(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[self.cache_key(request)].get(
            service.service_id, None)
        if not data:
            raise NotSupportedError(
                "FedEx does not support shipment of that package(s).")
        return data['price']

# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [FedExApi]