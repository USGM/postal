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
from ..data import Address


def get_directory_of(a):
    return os.path.split((os.path.abspath(inspect.getfile(a))))[0]


class FixBrokenRateNamespace(MessagePlugin):
    def marshalled(self, context):
        (context.envelope.getChild('Body').getChild('RateRequest')
            .getChild('Request')).prefix = 'ns0'


class FixBrokenAddressNamespace(MessagePlugin):
    def marshalled(self, context):
        (context.envelope.getChild('Body').getChild('XAVRequest')
            .getChild('Request')).prefix = 'ns0'


class FixBrokenTimeNamespace(MessagePlugin):
    def marshalled(self, context):
        (context.envelope.getChild('Body').getChild('TimeInTransitRequest')
            .getChild('Request')).prefix = 'ns0'


class FixBrokenShipmentRequestNamespace(MessagePlugin):
    def marshalled(self, context):
        (context.envelope.getChild('Body').getChild('ShipmentRequest')
            .getChild('Request')).prefix = 'ns0'


class AuthenticationPlugin(MessagePlugin):
    def __init__(self, username, password, access_license_number):
        self.username = username
        self.password = password
        self.access_license_number = access_license_number

    def marshalled(self, context):
        header = context.envelope.getChild('Header')

        security = Element('upss:UPSSecurity')
        security.set(
            'xmlns:upss', "http://www.ups.com/XMLSchema/XOLTWS/UPSS/v1.0"
        )

        header.append(security)

        username_token = Element('upss:UsernameToken')
        security.append(username_token)

        username = Element('upss:Username')
        username.setText(self.username)
        username_token.append(username)

        password = Element('upss:Password')
        password.setText(self.password)
        username_token.append(password)

        service_access_token = Element('upss:ServiceAccessToken')
        security.append(service_access_token)

        access_license_number = Element('upss:AccessLicenseNumber')
        access_license_number.setText(self.access_license_number)
        service_access_token.append(access_license_number)


Void = Client(
    'file://' + os.path.join(
        get_directory_of(inspect.currentframe()), 'wsdl', 'ups', 'Void.wsdl'
    ),
    cache=suds.cache.NoCache()
)


class UPSAPI(base.Carrier):
    name = 'UPS'

    def __init__(
        self, username, password, access_license_number, shipper_number,
        shipper_address
    ):
        super(UPSAPI, self).__init__()
        self.shipper_number = shipper_number
        self.shipper_address = shipper_address

        authentication = AuthenticationPlugin(
            username, password, access_license_number)

        self._RateWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'RateWS.wsdl'
            ),
            plugins=[authentication, FixBrokenRateNamespace()]
        )
        self._XAV = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'XAV.wsdl'
            ),
            plugins=[authentication, FixBrokenAddressNamespace()]
        )
        self._TNTWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'TNTWS.wsdl'
            ),
            plugins=[authentication, FixBrokenTimeNamespace()]
        )
        self._Ship = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'Ship.wsdl'
            ),
            cache=suds.cache.NoCache(),
            plugins=[authentication, FixBrokenShipmentRequestNamespace()]
        )
        self.TNTWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'TNTWS.wsdl'
            ),
            cache=suds.cache.NoCache(),
            plugins=[
                AuthenticationPlugin(
                    username, password, access_license_number
                ),
                FixBrokenTimeNamespace()
            ]
        )

    def ship(self, service, request):
        api_request = self._Ship.factory.create('ns0:RequestType')
        api_request.RequestOption = 'validate'

        api_shipment = self._Ship.factory.create('ns3:ShipmentType')
        api_shipment.Service.Code = service.service_id
        _populate_shipper(
            api_shipment.Shipper, self.shipper_address, self.shipper_number,
            True, True, '123456'
        )
        _populate_address(
            api_shipment.ShipTo, request.destination, use_phone=True,
            use_attn=True
        )
        _populate_address(
            api_shipment.ShipFrom,
            (
                request.origin
                if request.origin is not None else
                self.shipper_address
            ),
            use_phone=True, use_attn=True
        )

        shipment_charge = self._Ship.factory.create('ns3:ShipmentChargeType')
        api_shipment.PaymentInformation.ShipmentCharge = [shipment_charge]

        # A shipment charge type
        # of 01 = Transportation is
        # required. A shipment
        # charge type of 02 =
        # Duties and Taxes is not
        # required; however, this
        # charge type is invalid for
        # Qualified Domestic
        # Shipments. A Qualified
        # Domestic Shipment is
        # any shipment in which
        # one of the following
        # applies:1) The origin and
        # destination country is the
        # same2) US to PR
        # shipment3) PR to US
        # shipment4) The origin
        # and destination country
        # are both European
        # Union Countries and the
        # GoodsNotInFreeCirculati
        # on indicator is not
        # present5) The origin and
        # destination IATA code is
        # the same
        shipment_charge.Type = '01'
        shipment_charge.BillShipper.AccountNumber = self.shipper_number

        #print api_shipment
        #api_shipment.Package.Packaging = '02'
        #api_shipment.Package.Dimensions.UnitOfMeasurement.Code = 'IN'
        #api_shipment.Package.Dimensions.Length = '5'
        #api_shipment.Package.Dimensions.Width = '4'
        #api_shipment.Package.Dimensions.Height = '3'
        #api_shipment.Package.PackageWeight.UnitOfMeasurement.Code = 'LBS'
        #api_shipment.Package.PackageWeight.Weight = '6'

        #for pak in request.packages:
        #    pak_tag = self._Ship.factory.create('ns3:PackageType')
        #    pak_tag.Packaging = '02'
        #    pak_tag.Dimensions.UnitOfMeasurement.Code = 'IN'
        #    pak_tag.Dimensions.Length = str(pak.length)
        #    pak_tag.Dimensions.Width = str(pak.width)
        #    pak_tag.Dimensions.Height = str(pak.height)
        #    pak_tag.PackageWeight.UnitOfMeasurement.Code = 'LBS'
        #    pak_tag.PackageWeight.Weight = str(pak.weight)

        def package_to_package_type(package):
            pak = self._Ship.factory.create('ns3:PackageType')
            pak.Packaging.Code = '02'
            pak.Dimensions.UnitOfMeasurement.Code = 'IN'
            pak.Dimensions.Length = str(package.length)
            pak.Dimensions.Width = str(package.width)
            pak.Dimensions.Height = str(package.height)
            pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'
            pak.PackageWeight.Weight = str(package.weight)
            if is_oversized(package):
                pak.LargePackageIndicator = ''
            return pak

        api_shipment.Package = [
            package_to_package_type(a) for a in request.packages]

        label_spec = self._Ship.factory.create('ns3:LabelSpecificationType')
        receipt_spec = self._Ship.factory.create(
            'ns3:ReceiptSpecificationType')

        print self._Ship.service.ProcessShipment(
            api_request, api_shipment, label_spec, receipt_spec)

    def get_services(self, request):
        rates = self.request_rates(
            'Shop', request.packages, request.destination,
            ship_from=request.origin
        )

        rated_shipments = {}

        for rated_shipment in rates.RatedShipment:
            service = base.Service(
                self,
                rated_shipment.Service.Code,
                _service_code_to_description.get(
                    rated_shipment.Service.Code, None
                )
            )

            rated_shipments[service] = dict(
                price=_get_money(rated_shipment.TotalCharges),
                delivery_datetime=self.delivery_datetime(service, request),
                alerts=[
                    a.Description for a in rated_shipment.RatedShipmentAlert]
            )

        return rated_shipments

    def request_rates(
        self, request_type, packages, destination, service=None,
        ship_from=None
    ):
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

        ship_from_address:data.Address|None = The address of the warehouse to
            ship from or None if same as shipper's office
        """
        pickup_type = '06'
        customer_type = '00'

        pickup_type = str(pickup_type)
        if len(pickup_type) != 2:
            raise TypeError()
        customer_type = str(customer_type)
        if len(customer_type) != 2:
            raise TypeError()

        request = self._RateWS.factory.create('ns0:RequestType')
        request.RequestOption = [request_type]

        _pickup_type = self._RateWS.factory.create('ns2:CodeDescriptionType')
        _pickup_type.Code = pickup_type

        _customer_classification = self._RateWS.factory.create(
            'ns2:CodeDescriptionType'
        )
        _customer_classification.Code = customer_type

        shipment = self._RateWS.factory.create('ns2:ShipmentType')

        if request_type == 'Rate' and service is None:
            raise Exception()
        if request_type == 'Shop' and service is not None:
            raise Exception()

        if service is not None:
            shipment.Service.Code = service.service_id
            shipment.Service.Description = service.name

        _populate_shipper(
            shipment.Shipper, self.shipper_address, self.shipper_number)

        if ship_from is not None:
            _populate_address(shipment.ShipFrom, ship_from)
        else:
            _populate_address(shipment.ShipFrom, self.shipper_address)

        _populate_address(shipment.ShipTo, destination)

        paks = []
        for package in packages:
            pak = self._RateWS.factory.create('ns2:PackageType')

            pak.Dimensions.UnitOfMeasurement.Code = 'IN'
            pak.Dimensions.Length = str(package.length)
            pak.Dimensions.Width = str(package.width)
            pak.Dimensions.Height = str(package.height)
            pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'
            pak.PackageWeight.Weight = str(package.weight)
            if is_oversized(package):
                pak.LargePackageIndicator = ''

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
            # For FRS rating requests the only valid value is customer supplied
            #   packaging 02.
            ####################################################### TODO
            pak.PackagingType.Code = '21'

            paks.append(pak)
        shipment.Package = paks

        if (
            shipment.ShipFrom.Address.CountryCode in ('US', 'PR') and
            destination.country.alpha2 not in ('US', 'PR')
        ):
            # Required if the shipment is from
            # US/PR Outbound to non US/PR
            # destination with the
            # PackagingType of UPS PAK(04)
            raise NotImplementedError()
            shipment.InvoiceLineTotal.CurrencyCode = 'USD'
            shipment.InvoiceLineTotal.MonetaryValue = '0'

        rates = self._RateWS.service.ProcessRate(
            request, _pickup_type, _customer_classification, shipment)

        if rates.Response.ResponseStatus.Code != '1':  # 1 = Success
            raise Exception()

        #if hasattr(rates.Response, 'Alert'):
        #    for alert in rates.Response.Alert:
        #        print 'ALERT:', alert.Description

        return rates

    def validate_address(self, address):
        #print 'Validating:\n' + str(address)

        request = self._XAV.factory.create('ns0:RequestType')
        request.RequestOption = '3'  # validation and classification

        address_key = self._XAV.factory.create('ns2:AddressKeyFormatType')
        address_key.ConsigneeName = address.contact_name
        address_key.AddressLine = address.street_lines[0]
        address_key.PoliticalDivision2 = address.city
        address_key.PoliticalDivision1 = address.subdivision
        address_key.Urbanization = address.urbanization
        address_key.CountryCode = address.country.alpha2
        address_key.PostcodePrimaryLow = address.postal_code

        response = self._XAV.service.ProcessXAV(
            request,
            None,  # missing tag = street-level validation
            2,  # candidate list size
            address_key
        )

        if response.Response.ResponseStatus.Code != '1':
            raise Exception()

        #if hasattr(response.Response, 'Alert'):
        #    for alert in response.Response.Alert:
        #        print 'ALERT (' + str(address) + '): ' + alert.Description

        if not hasattr(response, 'Candidate'):
            #print 'No candidate attribute'
            #print response
            return False, None

        if len(response.Candidate) == 0:
            #print 'No elements in candidate attribute'
            return False, None

        candidate = response.Candidate[0]

        residential = candidate.AddressClassification.Code
        if residential == '0':  # unknown (usually for st # ranges)
            residential = None
        elif residential == '1':  # commercial
            residential = False
        elif residential == '2':  # residential
            residential = True
        else:
            raise Exception()  # TODO: make this a warning in a release version
            residential = None

        result = Address(
            contact_name=address.contact_name,
            phone_number=address.phone_number,
            street_lines=candidate.AddressKeyFormat.AddressLine,
            subdivision=candidate.AddressKeyFormat.PoliticalDivision1,
            city=candidate.AddressKeyFormat.PoliticalDivision2,
            postal_code=candidate.AddressKeyFormat.PostcodePrimaryLow + (
                '-' + candidate.AddressKeyFormat.PostcodeExtendedLow
                if candidate.AddressKeyFormat.PostcodeExtendedLow is not None
                else ''
            ),
            country=candidate.AddressKeyFormat.CountryCode,
            residential=(
                residential
                if residential is not None else
                address.residential  # if UPS doesn't know, use parameter
            ),
            urbanization=(
                candidate.AddressKeyFormat.Urbanization
                if hasattr(candidate.AddressKeyFormat, 'Urbanization') else
                None
            )
        )

        if result == address:
            return True, result
        else:
            return False, result

    def delivery_datetime(self, service, request):
        api_request = self._TNTWS.factory.create('ns0:RequestType')
        #request.RequestOption = 'TNT'  # just mimicking the example Perl app
        #request.RequestOption = str(service.service_id)

        api_request.RequestOption = ''  # Does not seem to matter what its
        # contents are as long as the tag is not missing.

        req_ship_from = self._TNTWS.factory.create('ns2:RequestShipFromType')
        if request.origin is not None:
            _populate_address(
                req_ship_from, request.origin,
                urbanization_title='Town', use_street=False, use_name=False
            )
        else:
            _populate_address(
                req_ship_from, self.shipper_address,
                urbanization_title='Town', use_street=False, use_name=False
            )

        req_ship_to = self._TNTWS.factory.create('ns2:RequestShipToType')
        _populate_address(
            req_ship_to, request.destination,
            urbanization_title='Town', use_street=False, use_name=False
        )

        sticks = self._TNTWS.factory.create('ns2:PickupType')
        ship_datetime = request.ship_datetime
        if request.ship_datetime is None:
            ship_datetime = datetime.now()
        sticks.Date = '%04d%02d%02d' % (  # YYYYMMDD
            ship_datetime.year,
            ship_datetime.month,
            ship_datetime.day
        )

        ### HHMM
        sticks.Time = '%02d%02d' % (ship_datetime.hour, ship_datetime.minute)

        weight = self._TNTWS.factory.create('ns2:ShipmentWeightType')
        weight.UnitOfMeasurement.Code = 'LBS'
        #weight.Weight = str(package.weight)
        weight.Weight = str(sum([package.weight for package in request.packages]))

        response = self._TNTWS.service.ProcessTimeInTransit(
            api_request,
            req_ship_from,
            req_ship_to,
            sticks,
            weight,
            str(len(request.packages)),  # num packages in shipment
            None,  # invoice TODO: implement this
            None,  # DocumentsOnlyIndicator (missing tag = false)

            # This field needs to
            # be populated when
            # UPS WorldWide
            # Express Freight
            # Shipment Service
            # is needed to be
            # returned in
            # response. The
            # valid value is 04.
            None,  # BillType

            None,  # MaximumListSize - default is 35

            None,  # SaturdayDeliveryInfoRequestIndicator
            # missing tag = no request

            None,  # DropOffAtFacilityIndicator
            # missing tag = pick up at warehouse

            # If indicator is
            # present indicates
            # pickup by cosignee
            # and if absent
            # indicates delivery
            # by UPS.This
            # accessorial is valid
            # if Bill Type is 04
            None  # HoldForPickupIndicator
        )

        if response.Response.ResponseStatus.Code != '1':
            raise Exception()

        for summary in response.TransitResponse.ServiceSummary:
            if (
                summary.Service.Code !=
                _service_code_to_time_in_transit_code[service.service_id]
            ):
                continue

            return datetime(
                year=int(summary.EstimatedArrival.Arrival.Date[0:4]),
                month=int(summary.EstimatedArrival.Arrival.Date[4:6]),
                day=int(summary.EstimatedArrival.Arrival.Date[6:8]),
                hour=int(summary.EstimatedArrival.Arrival.Time[0:2]),
                minute=int(summary.EstimatedArrival.Arrival.Time[2:4])
            )

        return None

    def quote(self, service, request):
        rates = self.request_rates(
            'Rate', request.packages, request.destination, service=service,
            ship_from=request.origin
        )

        if len(rates.RatedShipment) != 1:
            raise Exception()
        rated_shipment = rates.RatedShipment[0]
        if rated_shipment.Service.Code != service.service_id:
            raise Exception()

        return _get_money(rated_shipment.TotalCharges)


def is_oversized(package):
    ### Use >, not >=; per documentation, packages can be UP TO the
    ### dimensions below

    if package.weight > 150:  # in pounds
        return True
    H, W, L = sorted([package.length, package.width, package.height])

    if L > 108:  # in inches
        return True
    if L + W * 2 + H * 2 > 165:  # in inches
        return True
    return False


def _test_is_oversized():
    from ..data import Package
    assert is_oversized(Package(109, 1, 1, 15))
    assert not is_oversized(Package(108, 1, 1, 15))
    assert not is_oversized(Package(5, 5, 5, 5))
    assert is_oversized(Package(5, 5, 5, 151))
    assert not is_oversized(Package(5, 5, 5, 150))
    assert not is_oversized(Package(101, 16, 16, 20))
    assert is_oversized(Package(102, 16, 16, 20))
    assert is_oversized(Package(16, 102, 16, 20))
    assert is_oversized(Package(16, 16, 102, 20))
    assert is_oversized(Package(101, 16, 16, 151))
_test_is_oversized()


def _populate_address(
    node, address, urbanization_title='Urbanization', use_street=True,
    use_name=True, use_phone=False, use_attn=False
):
    """
    node = shipment.Shipper|shipment.ShipFrom|shipment.ShipTo
    """
    if use_name:
        node.Name = address.contact_name
    if use_street:
        node.Address.AddressLine = address.street_lines
    node.Address.City = address.city
    node.Address.StateProvinceCode = address.subdivision
    node.Address.PostalCode = address.postal_code
    node.Address.CountryCode = address.country.alpha2
    if urbanization_title is not None and address.urbanization is not None:
        setattr(node.Address, urbanization_title, address.urbanization)
    if address.residential:
        node.Address.ResidentialAddressIndicator = ''
    if use_phone:
        node.Phone.Number = address.phone_number
    if use_attn:
        node.AttentionName = address.contact_name


def _populate_shipper(
    node, address, shipper_number, use_attn=False, use_phone=False,
    tax_identification_number=None
):
    _populate_address(node, address, use_phone=use_phone, use_attn=use_attn)
    node.ShipperNumber = shipper_number
    if tax_identification_number is not None:
        node.TaxIdentificationNumber = tax_identification_number


def _get_money(node):
    return money.Money(node.MonetaryValue, node.CurrencyCode)


_service_code_to_description = {

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

_service_code_to_time_in_transit_code = {
    '14': '1DM',
    '01': '1DA',
    '13': '1DP',
    '59': '2DM',
    '02': '2DA',
    '12': '3DS',
    '03': 'GND',
    '54': '21',
    '07': '01',
    '08': '05',
    '11': '03',
    '65': '20',
    '96': '29'  # UPS Worldwide Express Freight

    ### No mappings:
    # UPS Next Day Air Early A.M. (Saturday Delivery)
    # UPS Next Day Air (Saturday Delivery)
    # UPS Second Day Air (Saturday Delivery)
    #?: '28'  # UPS Worldwide Saver
    #?: 'G'  # UPS Ground ---- Puerto Rico to United States and United States to Puerto Rico
}
