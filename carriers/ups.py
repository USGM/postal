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



def ship():
    print Ship


service_code_to_description = {
    '01': 'UPS Next Day Air',  # 'UPS Express' if shipping from Canada
    '02': 'UPS Second Day Air',
    # 'UPS Worldwide ExpeditedSM' - 02 Rating, 08 Shipping, if shipping from Canada
    '03': 'UPS Ground',
    '07': 'UPS Worldwide ExpressSM',  # different names when originating from other countries
    '08': 'UPS Worldwide ExpeditedSM',  # different names when originating from other countries
    '11': 'UPS Standard',
    '12': 'UPS Three-Day Select',
    '13': 'UPS Next Day Air Saver',
    '14': 'UPS Next Day Air Early A.M. SM',  # different name when originating from Canada
    '54': 'UPS Worldwide Express Plus SM',  # different name when originating from Mexico
    '59': 'UPS Second Day Air A.M.',
    '65': 'UPS Saver',
    '96': 'UPS Worldwide Express Freight'
    ### leaving out a few that are Polish-only
}





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
    pickup_type = str(pickup_type)
    if len(pickup_type) != 2:
        raise TypeError()
    customer_type = str(customer_type)
    if len(customer_type) != 2:
        raise TypeError()

    #print dir(RateWS.service)
    #print Ship

    #print RateWS
    #print
    #print '***** REQUEST TYPE *****'
    #print RateWS.factory.create('ns0:RequestType')
    #print '***** REQUEST OPTION *****'
    #print RateWS.factory.create('ns0:RequestOption')
    #print
    #print '***** CODE DESCRIPTION TYPE *****'
    #print RateWS.factory.create('ns2:CodeDescriptionType')
    #print
    #print '***** SHIPMENT TYPE *****'
    #print RateWS.factory.create('ns2:ShipmentType')


    try:
        request = RateWS.factory.create('ns0:RequestType')
        if request_type:
            request.RequestOption = [request_type]
        print '**********************'
        #print request
        #print dir(request)
        #print dir(request.RequestOption)

        _pickup_type = RateWS.factory.create('ns2:CodeDescriptionType')
        _pickup_type.Code = pickup_type
        #print _pickup_type


        _customer_classification = RateWS.factory.create('ns2:CodeDescriptionType')
        _customer_classification.Code = customer_type
        #print _customer_classification


        shipment = RateWS.factory.create('ns2:ShipmentType')

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

        shipment.ShipTo.Name = 'John Doe'
        shipment.ShipTo.Address.AddressLine = ['123 Main St']
        shipment.ShipTo.Address.City = 'Houston'
        shipment.ShipTo.Address.StateProvinceCode = 'TX'
        shipment.ShipTo.Address.PostalCode = '77047'
        shipment.ShipTo.Address.CountryCode = 'US'

        residential = False  # TODO
        if residential:
            shipment.ShipTo.Address.ResidentialAddressIndicator = ''

        if request_type == 'Rate':
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
            shipment.Service.Code = 'asdf'

        pak = RateWS.factory.create('ns2:PackageType')

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

        # Dimensions not for FRS
        pak.Dimensions.UnitOfMeasurement.Code = 'IN'  # IN or CM
        #pak.Dimensions.Length = '%6.2f' % 5
        #pak.Dimensions.Width = '%6.2f' % 4
        #pak.Dimensions.Height = '%6.2f' % 3
        pak.Dimensions.Length = '5'
        pak.Dimensions.Width = '4'
        pak.Dimensions.Height = '3'

        # Weight required for FRS
        pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'  # LBS or KGS
        #pak.PackageWeight.Weight = '%6.1f' % 6
        pak.PackageWeight.Weight = '6'


        #print pak
        shipment.Package = [pak]

        us_pr_to_non_us_pr_and_ups_pak = False
        if us_pr_to_non_us_pr_and_ups_pak:
            # Required if the shipment is from
            # US/PR Outbound to non US/PR
            # destination with the
            # PackagingType of UPS PAK(04)
            shipment.InvoiceLineTotal.CurrencyCode = 'USD'
            shipment.InvoiceLineTotal.MonetaryValue = '0'

        #print shipment


        rates = RateWS.service.ProcessRate(request, _pickup_type, _customer_classification, shipment)

        if rates.Response.ResponseStatus.Code != '1':  # 1 = Success
            raise Exception()

        for alert in rates.Response.Alert:
            print 'ALERT:', alert.Description

        #print rates
        #print rates.RatedShipment[0]

        rated_shipments = []

        for rated_shipment in rates.RatedShipment:
            print ' --- '
            print (
                service_code_to_description[rated_shipment.Service.Code]
                if rated_shipment.Service.Code in service_code_to_description else
                'Service#:' + rated_shipment.Service.Code + 'Unknown Service'
            )
            for alert in rated_shipment.RatedShipmentAlert:
                print 'ALERT:', alert.Description
            print 'Total cost:', rated_shipment.TotalCharges.MonetaryValue, rated_shipment.TotalCharges.CurrencyCode
            print (
                'Guaranteed to be delivered within ' + rated_shipment.GuaranteedDelivery.BusinessDaysInTransit +
                ' business days'
                + (', by ' + rated_shipment.GuaranteedDelivery.DeliveryByTime if hasattr(rated_shipment.GuaranteedDelivery, 'DeliveryByTime') else '')
            )

            rated_shipments.append((
                rated_shipment.Service.Code,
                money.Money(rated_shipment.TotalCharges.MonetaryValue, rated_shipment.TotalCharges.CurrencyCode),
                (
                    rated_shipment.GuaranteedDelivery.BusinessDaysInTransit,
                    rated_shipment.GuaranteedDelivery.DeliveryByTime if hasattr(rated_shipment.GuaranteedDelivery, 'DeliveryByTime') else None
                )
            ))

            base.Service(
                None,  # carrier
                rated_shipment.Service.Code,
                service_code_to_description.get(rated_shipment.Service.Code, None)
            )

        print rated_shipments


    except WebFault as err:
        #print err.fault.detail.Errors.ErrorDetail.PrimaryErrorCode.Code
        print
        print '***** FAULT *****'
        print err.fault
        print err.message
