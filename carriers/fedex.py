"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import os
import re
from suds import WebFault

from suds.client import Client
from suds.plugin import MessagePlugin
from money import Money

from base import Carrier, Service
from ..exceptions import CarrierError, ExceedsLimitsError


class ClearEmpty(MessagePlugin):
    def clear_empty_tags(self, tags):
        for tag in tags:
            children = tag.getChildren()[:]
            if children:
                self.clear_empty_tags(children)
            if re.match(r'^<[^>]+?/>$', tag.plain()):
                tag.parent.remove(tag)

    def marshalled(self, context):
        self.clear_empty_tags(context.envelope.getChildren()[:])


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
        'GROUND_HOME_DELIVERY': 'Ground Home Delivery'}

    def __init__(self, key, account_number, password, meter_number):
        self.key = key
        self.account_number = account_number
        self.password = password
        self.meter_number = meter_number
        self.cache = {}

        base_path = os.path.split(os.path.abspath(
            inspect.getfile(inspect.currentframe())))[0]
        base_path = os.path.join(base_path, 'wsdl', 'fedex')
        full_path = os.path.join(base_path, 'RateService_v14.wsdl')
        url = "file://%s" % full_path

        self.rates_client = Client(url, plugins=[ClearEmpty()])

        full_path = os.path.join(
            base_path, 'PackageMovementInformationService_v5.wsdl')
        url = "file://%s" % full_path
        self.movement_client = Client(url, plugins=[ClearEmpty()])

        self.contact_type = (
            self.rates_client.factory.create('Party').__class__)

    def authentication(self):
        auth = self.rates_client.factory.create('WebAuthenticationDetail')
        keys = self.rates_client.factory.create('WebAuthenticationCredential')
        keys.Key = self.key
        keys.Password = self.password
        auth.UserCredential = keys
        return auth

    def user_client(self):
        client = self.rates_client.factory.create('ClientDetail')
        client.AccountNumber = self.account_number
        client.MeterNumber = self.meter_number
        client.Localization.LanguageCode = 'EN'
        client.Localization.LocaleCode = 'us'
        return client

    def transaction_detail(self):
        return self.rates_client.factory.create('TransactionDetail')

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

    def set_address(self, target, address, contact=True):
        target_address = target.Address
        if isinstance(contact, self.contact_type):
            target_contact = target.Contact
            target_address = target.Address
            target_contact.PersonName = address.contact_name
            target_contact.PhoneNumber = address.phone_number
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

    def rate_response_dict(self, response):
        return {
            method.ServiceType: {
                'service': method.ServiceType,
                'price': method.RatedShipmentDetails[
                    0].RatedPackages[0].PackageRateDetail.NetCharge,
                'delivery_date': getattr(method, 'DeliveryTimestamp', None)}
            for method in response.RateReplyDetails}

    def create_service(self, service, specs):
        return Service(
            self, service, self.service_table[service], specs['delivery_date'])

    def get_services(self, package):
        """
        Get available services for shipping a package.
        """
        auth = self.authentication()
        client = self.user_client()
        transaction_detail = self.transaction_detail()
        version = self.rates_version_id()
        return_transit = True
        codes = self.carrier_codes()
        variable_options = []
        requested_shipment = self.requested_shipment(package)
        response = self.service_call(self.rates_client, 'getRates',
            auth, client, transaction_detail, version, return_transit, codes,
            variable_options, requested_shipment)
        result = self.rate_response_dict(response)
        self.cache_results(package, result)

        final = [
            self.create_service(key, value) for key, value in result.items()]

        return final

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