__author__ = 'Nathan Everitt'

import inspect
import os

from suds.client import Client
from suds.plugin import MessagePlugin
from suds.sax.element import Element
from suds import WebFault
import suds.cache
import money
import base
from datetime import datetime


def get_directory_of(a):
    return os.path.split((os.path.abspath(inspect.getfile(a))))[0]



class FixBrokenNamespacePlugin(MessagePlugin):
    def marshalled(self, context):
        context.envelope.getChild('Body').getChild('RateRequest').getChild('Request').prefix = 'ns0'


class AuthenticationPlugin(MessagePlugin):
    def marshalled(self, context):
        header = context.envelope.getChild('Header')

        security = Element('upss:UPSSecurity')
        security.set('xmlns:upss', "http://www.ups.com/XMLSchema/XOLTWS/UPSS/v1.0")

        header.append(security)

        username_token = Element('upss:UsernameToken')
        security.append(username_token)

        username = Element('upss:Username')
        username.setText('')
        username_token.append(username)

        password = Element('upss:Password')
        password.setText('')
        username_token.append(password)

        service_access_token = Element('upss:ServiceAccessToken')
        security.append(service_access_token)

        access_license_number = Element('upss:AccessLicenseNumber')
        access_license_number.setText('')
        service_access_token.append(access_license_number)


RateWS = Client(
    'file://' + os.path.join(get_directory_of(inspect.currentframe()), 'wsdl', 'ups', 'RateWS.wsdl'),
    cache=suds.cache.NoCache(),
    plugins=[AuthenticationPlugin(), FixBrokenNamespacePlugin()]
)


Void = Client(
    'file://' + os.path.join(get_directory_of(inspect.currentframe()), 'wsdl', 'ups', 'Void.wsdl'),
    cache=suds.cache.NoCache()
)

Ship = Client(
    'file://' + os.path.join(get_directory_of(inspect.currentframe()), 'wsdl', 'ups', 'Ship.wsdl'),
    cache=suds.cache.NoCache()
)



class UPSAPI(base.Carrier):

    name = 'UPS'

    def __init__(self):
        super(UPSAPI, self).__init__()

    def get_services(self, package):
        return self.get_services_list([package], package.destination)

    def get_services_list(self, packages, destination):
        rates = self.request_rates('Shop', packages, destination)

        rated_shipments = {}

        for rated_shipment in rates.RatedShipment:
            rated_shipments[base.Service(
                self,
                rated_shipment.Service.Code,
                _service_code_to_description.get(rated_shipment.Service.Code, None)
            )] = _get_rated_shipment_info(rated_shipment)

        return rated_shipments

    def request_rates(self, request_type, packages, destination, service=None):
        """
        request_type = 'Rate'|'Shop'
            Rate = The server rates (The
            default rates if an option is not
            provided).
            Shop = The server validates the
            shipment, and return rates for all
            UPS products from the
            ShipFrom to the ShipTo
            addresses.

        pickup_type = one of:
            '01' - Daily Pickup
            '03' - Customer Counter
            '06' - One Time Pickup
            '07' - On Call Air
            '19' - Letter Center
            '20' - Air Service Center

        customer_type = one of
            00 - Rates Associated with Shipper Number
            01 - Daily Rates
            04 - Retail Rates
            53 - Standard List Rates
        """
        pickup_type = '06'
        customer_type = '00'

        pickup_type = str(pickup_type)
        if len(pickup_type) != 2:
            raise TypeError()
        customer_type = str(customer_type)
        if len(customer_type) != 2:
            raise TypeError()

        request = RateWS.factory.create('ns0:RequestType')
        request.RequestOption = [request_type]

        _pickup_type = RateWS.factory.create('ns2:CodeDescriptionType')
        _pickup_type.Code = pickup_type

        _customer_classification = RateWS.factory.create('ns2:CodeDescriptionType')
        _customer_classification.Code = customer_type

        shipment = RateWS.factory.create('ns2:ShipmentType')

        if service is not None:
            shipment.Service.Code = service.service_id
            shipment.Service.Description = service.name

        _populate_origin(shipment)
        _populate_destination(shipment, destination)

        residential = False  # TODO
        if residential:
            shipment.ShipTo.Address.ResidentialAddressIndicator = ''

        paks = []
        for package in packages:
            pak = RateWS.factory.create('ns2:PackageType')

            pak.Dimensions.UnitOfMeasurement.Code = 'IN'
            pak.Dimensions.Length = str(package.length)
            pak.Dimensions.Width = str(package.width)
            pak.Dimensions.Height = str(package.height)
            pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'
            pak.PackageWeight.Weight = str(package.weight)

            # 00 = Unknown
            # 01 = UPS Letter
            # 02 = Package/customer supplied
            # 03 = UPS Tube
            # 04 = UPS Pak
            # 21 = Express Box
            # 24 = 25KG Box
            # 25 = 10KG Box
            # 30 = Pallet
            # 2a = Small Express Box
            # 2b = Medium Express Box
            # 2c = Large Express Box
            # For FRS rating requests the only valid value is customer supplied packaging 02.
            pak.PackagingType.Code = '21'

            paks.append(pak)
        shipment.Package = paks

        if shipment.ShipFrom.Address.CountryCode in ('US', 'PR') and destination.country.alpha2 not in ('US', 'PR'):
            # Required if the shipment is from
            # US/PR Outbound to non US/PR
            # destination with the
            # PackagingType of UPS PAK(04)
            raise NotImplementedError()
            shipment.InvoiceLineTotal.CurrencyCode = 'USD'
            shipment.InvoiceLineTotal.MonetaryValue = '0'

        #print request
        #print shipment
        rates = RateWS.service.ProcessRate(request, _pickup_type, _customer_classification, shipment)

        if rates.Response.ResponseStatus.Code != '1':  # 1 = Success
            raise Exception()

        #for alert in rates.Response.Alert:
        #    print 'ALERT:', alert.Description
        return rates

    def validate_address(self, address):
        """
        If the carrier implements address validation services, you can set
        those up here.

        This should return a true or false value, as well as a new address
        object, comprised of any fixes upstream sends.
        """
        raise NotImplementedError

    def delivery_datetime(self, service, package):
        return self.delivery_datetime_list(service, [package], package.destination)

    def delivery_datetime_list(self, service, packages, destination):
        rates = self.request_rates('Rate', packages, destination, service=service)

        if len(rates.RatedShipment) != 1:
            raise Exception()
        rated_shipment = rates.RatedShipment[0]
        if rated_shipment.Service.Code != service.service_id:
            raise Exception()

        return _get_rated_shipment_info(rated_shipment)

    def quote(self, service, package):
        """
        Given a service and a package, determine the cost of sending the
        package through that service. If the package cannot be sent through
        that service, an exception should be raised.
        """
        raise NotImplementedError


def _guaranteed_delivery_to_string(delivery):
    return (
        'Delivery within ' + delivery.BusinessDaysInTransit + ' business day'
        + ('s' if delivery.BusinessDaysInTransit != '1' else '')
        + (' by ' + delivery.DeliveryByTime if hasattr(delivery, 'DeliveryByTime') else '')
    )

def _populate_origin(shipment):
    shipment.Shipper.Name = 'US Global Mail'
    shipment.Shipper.ShipperNumber = ''
    shipment.Shipper.Address.AddressLine = ['1321 Upland Drive']
    shipment.Shipper.Address.City = 'Houston'
    shipment.Shipper.Address.StateProvinceCode = 'TX'
    shipment.Shipper.Address.PostalCode = '77043'
    shipment.Shipper.Address.CountryCode = 'US'

    shipment.ShipFrom.Name = 'US Global Mail'
    shipment.ShipFrom.Address.AddressLine = ['1321 Upland Drive']
    shipment.ShipFrom.Address.City = 'Houston'
    shipment.ShipFrom.Address.StateProvinceCode = 'TX'
    shipment.ShipFrom.Address.PostalCode = '77043'
    shipment.ShipFrom.Address.CountryCode = 'US'

def _populate_destination(shipment, destination):
    shipment.ShipTo.Name = destination.contact_name
    shipment.ShipTo.Address.AddressLine = list(destination.street_lines)
    shipment.ShipTo.Address.City = destination.city
    shipment.ShipTo.Address.StateProvinceCode = destination.subdivision
    shipment.ShipTo.Address.PostalCode = destination.postal_code
    shipment.ShipTo.Address.CountryCode = destination.country.alpha2
    if destination.residential:
        shipment.ShipTo.Address.ResidentialAddressIndicator = ''

def _get_rated_shipment_info(rated_shipment):
    info = dict(price=money.Money(rated_shipment.TotalCharges.MonetaryValue, rated_shipment.TotalCharges.CurrencyCode))
    try:
        info['delivery_datetime'] = _guaranteed_delivery_to_string(rated_shipment.GuaranteedDelivery)
        #datetime.datetime.now()
    except AttributeError:
        info['delivery_datetime'] = None

    return info


_service_code_to_description = {
    '01': 'UPS Next Day Air',  # 'UPS Express' if shipping from Canada
    '02': 'UPS Second Day Air',
    # 'UPS Worldwide Expedited' - 02 Rating, 08 Shipping, if shipping from Canada
    '03': 'UPS Ground',
    '07': 'UPS Worldwide Express',  # different names when originating from other countries
    '08': 'UPS Worldwide Expedited',  # different names when originating from other countries
    '11': 'UPS Standard',
    '12': 'UPS Three-Day Select',
    '13': 'UPS Next Day Air Saver',
    '14': 'UPS Next Day Air Early A.M.',  # different name when originating from Canada
    '54': 'UPS Worldwide Express Plus',  # different name when originating from Mexico
    '59': 'UPS Second Day Air A.M.',
    '65': 'UPS Saver',
    '96': 'UPS Worldwide Express Freight'
    ### leaving out a few that are Polish-only
}
### from docs:
# 01 = Next Day Air
# 02 = 2nd Day Air
# 03 = Ground
# 12 = 3 Day Select
# 13 = Next Day Air Saver
# 14 = Next Day Air Early AM
# 59 = 2nd Day Air AM
#
# Valid international values:
# 07 = Worldwide Express
# 08 = Worldwide Expedited
# 11 = Standard
# 54 = Worldwide Express Plus
# 65 = UPS Saver. Required for Rating and Ignored for Shopping
# ? = WorldWide Express Saver Freight
#
# Valid Poland to Poland Same
# Day values:
# 82 = UPS Today Standard
# 83 = UPS Today Dedicated
# Courier
# 84 = UPS Today Intercity
# 85 = UPS Today Express
# 86 = UPS Today Express Saver
# 96 = UPS Worldwide Express Freight
#
# Code for the UPS Service associated with
# the shipment Note: The valid service code for
# a FRS Rating Request is
# 03=Ground





def request_rate(request_type, pickup_type, customer_type):
    """
    request_type = 'Rate'|'Shop'
        Rate = The server rates (The
        default rates if an option is not
        provided).
        Shop = The server validates the
        shipment, and return rates for all
        UPS products from the
        ShipFrom to the ShipTo
        addresses.

    pickup_type = one of:
        '01' - Daily Pickup
        '03' - Customer Counter
        '06' - One Time Pickup
        '07' - On Call Air
        '19' - Letter Center
        '20' - Air Service Center

    customer_type = one of
        00 - Rates Associated with Shipper Number
        01 - Daily Rates
        04 - Retail Rates
        53 - Standard List Rates
    """
    # 00 = Unknown
    # 01 = UPS Letter
    # 02 = Package/customer
    # supplied
    # 03 = UPS Tube
    # 04 = UPS Pak
    # 21 = Express Box
    # 24 = 25KG Box
    # 25 = 10KG Box
    # 30 = Pallet
    # 2a = Small Express Box
    # 2b = Medium Express Box
    # 2c = Large Express Box
    # For FRS rating requests the only valid value is customer supplied packaging 02.
    pak.PackagingType.Code = '21'
