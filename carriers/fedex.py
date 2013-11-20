"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import os
from suds.client import Client
from base import Carrier


class FedExApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    def __init__(self, key, account_number, password, meter_number):
        self.key = key
        self.account_number = account_number
        self.password = password
        self.meter_number = meter_number

        base_path = os.path.split(os.path.abspath(
            inspect.getfile(inspect.currentframe())))[0]
        base_path = os.path.join(base_path, 'wsdl', 'fedex')
        full_path = os.path.join(base_path, 'RateService_v14.wsdl')
        url = "file://%s" % full_path

        self.rates_client = Client(url)

        full_path = os.path.join(
            base_path, 'PackageMovementInformationService_v5.wsdl')
        url = "file://%s" % full_path
        self.movement_client = Client(url)

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
        return [codes.FDXC, codes.FDXE, codes.FDXG]

    def service_options(self):
        options = self.rates_client.factory.create('ServiceOptionType')
        return [options.SATURDAY_DELIVERY]

    def line_item(self, package):
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

        return item

    @staticmethod
    def set_address(target, address):
        target.Contact.PersonName = address.contact_name
        target.Contact.PhoneNumber = address.phone_number
        target.Address.StreetLines = address.street_lines
        target.Address.City = address.city
        target.Address.PostalCode = address.postal_code
        target.Address.CountryCode = address.country.alpha2
        target.Address.CountryName = address.country.name
        target.Address.StateOrProvinceCode = address.subdivision

    def requested_shipment(self, package):
        request = self.rates_client.factory.create('RequestedShipment')

        packaging = self.rates_client.factory.create('PackagingType')
        request.PackagingType = packaging.YOUR_PACKAGING

        self.set_address(request.Shipper, package.origin)
        self.set_address(request.Recipient, package.destination)

        payment = request.ShippingChargesPayment
        payment.PaymentType.value = 'SENDER'
        payment.Payor.ResponsibleParty.AccountNumber = self.account_number
        self.set_address(payment.Payor.ResponsibleParty, package.origin)

        request.RateRequestTypes = 'LIST'
        request.PackageCount = 1

        request.RequestedPackageLineItems = [self.line_item(package)]

        return request

    def get_services(self, package):
        """
        Get available services for shipping a package.
        """
        auth = self.authentication()
        client = self.user_client()
        transaction_detail = self.transaction_detail()
        version = self.rates_version_id()
        return_transit = False
        codes = []
        requested_shipment = self.requested_shipment(package)
        print self.rates_client.service.getRates(
            auth, client, transaction_detail, version, return_transit, codes,
            requested_shipment)

    def quote(self, service, package):
        pass

# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [FedExApi]