"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import os
from datetime import datetime

from suds.client import Client
from money import Money

from base import Carrier, Service, ClearEmpty
from ..exceptions import ExceedsLimitsError
from ..data import Address


class FedExApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    name = 'FedEx'
    service_table = {
        'FIRST_OVERNIGHT': 'First Overnight',
        'PRIORITY_OVERNIGHT': 'Priority Overnight',
        'STANDARD_OVERNIGHT': 'Standard Overnight',
        'FEDEX_2_DAY': '2Day',
        'FEDEX_2_DAY_AM': '2Day AM delivery',
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
        'FEDEX_3_DAY_FREIGHT': '3 Day Freight',
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
        return Client(self.service_url(wsdl_name), plugins=[ClearEmpty()])

    def __init__(self, key, account_number, password, meter_number):
        super(FedExApi, self).__init__()
        self.key = key
        self.account_number = account_number
        self.password = password
        self.meter_number = meter_number
        self.cache = {}

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
            self.address_client, 'addressValidation',
            auth, client_detail, transaction_detail, version_id,
            request_timestamp, address_validation_options, address_item)
        result = result.AddressResults[0][0][0]
        success = result.Score
        address = self.address_from_validator(result, address)
        return success, address

    def rates_version_id(self):
        version = self.rates_client.factory.create('VersionId')
        version.ServiceId = 'crs'
        version.Major = 14
        version.Intermediate = 0
        version.Minor = 0
        return version

    def carrier_codes(self):
        codes = self.rates_client.factory.create('CarrierCodeType')
        return [codes.FDXE, codes.FDXG]

    def line_item(self, request, package):
        item = self.rates_client.factory.create('RequestedPackageLineItem')
        item.SequenceNumber = 1
        item.GroupPackageCount = 1
        item.Weight.Units.value = 'KG'
        item.Weight.Value = int(round(package.weight))

        dimensions = item.Dimensions
        dimensions.Height = int(round(package.height))
        dimensions.Width = int(round(package.width))
        dimensions.Length = int(round(package.length))
        dimensions.Units = 'CM'

        if package.declarations:
            value = self.set_declarations(request, package)
            if value and package.insure:
                item.InsuredValue.Currency = value.currency
                item.InsuredValue.Amount = value.amount

        return item

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

    def set_declarations(self, request, package):
        commodities = []
        total_value = None
        for declaration in package.declarations:
            commodity = self.rates_client.factory.create('Commodity')
            commodity.Description = declaration.description
            value = declaration.value
            commodity.UnitPrice.Currency = value.currency
            commodity.UnitPrice.Amount = value.amount
            value = value * declaration.units
            commodity.CustomsValue.Currency = value.currency
            commodity.CustomsValue.Amount = value.amount
            commodities.append(commodity)
            if not total_value:
                total_value = value
            else:
                total_value += value
        request.CustomsClearanceDetail.Commodities = commodities
        return total_value

    def requested_shipment(self, package):
        request = self.rates_client.factory.create('RequestedShipment')

        self.set_address(request.Shipper, package.origin)
        self.set_address(request.Recipient, package.destination)

        request.RateRequestTypes = 'ACCOUNT'
        request.PackageCount = 1

        request.RequestedPackageLineItems = [self.line_item(request, package)]
        request.ShipTimestamp = package.ship_datetime

        return request

    def cache_results(self, package, response):
        """
        Avoid looking up information on an object more than we must.
        """
        # For now, we make this in-process.
        self.cache.update({package: response})

    @staticmethod
    def rate_response_dict(response):
        if not hasattr(response, 'RateReplyDetails'):
            return {}
        return {
            method.ServiceType: {
                'service': method.ServiceType,
                'price': method.RatedShipmentDetails[
                    0].ShipmentRateDetail.TotalNetCharge,
                'delivery_datetime': getattr(
                    method, 'DeliveryTimestamp', None)}
            for method in response.RateReplyDetails}

    def create_service(self, service):
        return Service(
            self, service, self.service_table[service])

    def get_services(self, package):
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
        requested_shipment = self.requested_shipment(package)
        response = self.service_call(
            self.rates_client, 'getRates',
            auth, client, transaction_detail, version, return_transit, codes,
            variable_options, requested_shipment)
        result = self.rate_response_dict(response)
        self.cache_results(package, result)

        final = [
            self.create_service(key) for key in result.keys()]

        return final

    def delivery_datetime(self, service, package):
        if not package in self.cache:
            self.get_services(package)
        data = self.cache[package].get(service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return data['delivery_datetime']

    def quote(self, service, package):
        if not package in self.cache:
            self.get_services(package)
        data = self.cache[package].get(service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return Money(data['price'].Amount, data['price'].Currency)

# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [FedExApi]