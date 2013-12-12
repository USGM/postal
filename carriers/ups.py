__author__ = 'Nathan Everitt'

import inspect
import os
import cStringIO
import base64

import PIL.Image
from suds.client import Client
from suds.plugin import MessagePlugin
from suds.sax.element import Element
from suds import WebFault
import suds.cache
import money
import base
from datetime import datetime
from ..data import Address, Shipment


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


def _on_webfault(webfault):
    raise Exception(
        'Webfault#'
        + webfault.fault.detail.Errors.ErrorDetail.PrimaryErrorCode.Code
        + ': '
        + webfault.fault.detail.Errors.ErrorDetail.PrimaryErrorCode.Description
    )


class UPSAPI(base.Carrier):
    name = 'UPS'
    address_validation = True

    def __init__(
        self, username, password, access_license_number, shipper_number,
        shipper_address=None
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

    def ship(self, service, request, receiver_account_number=None):
        api_request = self._Ship.factory.create('ns0:RequestType')
        api_request.RequestOption = 'validate'

        api_shipment = self._Ship.factory.create('ns3:ShipmentType')
        api_shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = ''
        api_shipment.Service.Code = service.service_id

        shipper_address = self.shipper_address
        if shipper_address is None:
            shipper_address = request.origin
            if shipper_address is None:
                raise Exception()
        _populate_shipper(
            api_shipment.Shipper, self.shipper_address, self.shipper_number,
            True, True, '123456'
        )
        _populate_address(
            api_shipment.ShipTo, request.destination, use_phone=True,
            use_attn=True
        )

        ship_from = (
            request.origin
            if request.origin is not None else
            self.shipper_address
        )
        _populate_address(
            api_shipment.ShipFrom, ship_from, use_phone=True, use_attn=True)

        international = (ship_from.country != request.destination.country)

        shipper_charge = self._Ship.factory.create('ns3:ShipmentChargeType')
        api_shipment.PaymentInformation.ShipmentCharge = [shipper_charge]

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
        shipper_charge.Type = '01'
        shipper_charge.BillShipper.AccountNumber = self.shipper_number

        if international:
            bill_receiver = self._Ship.factory.create('ns3:ShipmentChargeType')
            bill_receiver.Type = '02'

            ### Evidently, if this is blank, UPS will contact the receiver
            ### in order to acquire billing information.
            bill_receiver.BillReceiver.AccountNumber = receiver_account_number

        def package_to_package_type(package):
            pak = self._Ship.factory.create('ns3:PackageType')
            pak.Packaging.Code = '02'  # customer-supplied packaging
            pak.Dimensions.UnitOfMeasurement.Code = 'IN'
            pak.Dimensions.Length = str(package.length)
            pak.Dimensions.Width = str(package.width)
            pak.Dimensions.Height = str(package.height)
            pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'
            pak.PackageWeight.Weight = str(package.weight)
            if is_large(package):
                pak.LargePackageIndicator = ''

            if (
                (len(package.declarations) > 0 and request.insure)
                or international
            ):
                _populate_money(
                    pak.PackageServiceOptions.DeclaredValue,
                    package.get_total_declared_value()
                )
            return pak

        api_shipment.Package = [
            package_to_package_type(a) for a in request.packages]


        api_shipment.Description = ', '.join([
            a.description

            ### flatten list of lists of declarations
            for a in sum([b.declarations for b in request.packages], [])

            ### truncate to 50 characters because UPS is S.P.E.C.I.A.L.
        ])[0:50]


        label_spec = self._Ship.factory.create('ns3:LabelSpecificationType')
        label_spec.LabelImageFormat.Code = 'GIF'

        receipt_spec = self._Ship.factory.create(
            'ns3:ReceiptSpecificationType')

        try:
            response = self._Ship.service.ProcessShipment(
                api_request, api_shipment, label_spec, receipt_spec)
        except WebFault as err:
            _on_webfault(err)
        #print response

        if response.Response.ResponseStatus.Code != '1':
            raise Exception()

        master_tracking_number = \
            response.ShipmentResults.ShipmentIdentificationNumber

        packages = {}
        i = 0
        for pak in response.ShipmentResults.PackageResults:
            pdf = cStringIO.StringIO()

            PIL.Image.open(cStringIO.StringIO(
                base64.b64decode(pak.ShippingLabel.GraphicImage))) \
                .transpose(PIL.Image.ROTATE_270) \
                .crop((0, 0, 800, 1200)) \
                .save(pdf, 'PDF', resolution=200.0)

            packages[request.packages[i]] = {
                'tracking_number': pak.TrackingNumber,
                'label': pdf.getvalue()
            }
            i += 1

        return Shipment(self, master_tracking_number, packages)

    def get_services(self, request):
        rates = self._request_rates(request, 'Shop')

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

    def _request_rates(self, request, request_type, service=None):
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

        ship_from:data.Address|None = The address of the warehouse to
            ship from or None if same as shipper's office
        """
        pickup_type = '01'
        customer_type = '00'

        api_request = self._RateWS.factory.create('ns0:RequestType')
        api_request.RequestOption = [request_type]

        _pickup_type = self._RateWS.factory.create('ns2:CodeDescriptionType')
        _pickup_type.Code = pickup_type

        _customer_classification = self._RateWS.factory.create(
            'ns2:CodeDescriptionType')
        _customer_classification.Code = customer_type

        shipment = self._RateWS.factory.create('ns2:ShipmentType')
        shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = ''

        if request_type == 'Rate' and service is None:
            raise Exception()
        if request_type == 'Shop' and service is not None:
            raise Exception()

        if service is not None:
            shipment.Service.Code = service.service_id
            shipment.Service.Description = service.name

        shipper_address = self.shipper_address
        if shipper_address is None:
            shipper_address = request.origin
            if shipper_address is None:
                raise Exception()

        _populate_shipper(
            shipment.Shipper, shipper_address, self.shipper_number)

        if request.origin is not None:
            _populate_address(shipment.ShipFrom, request.origin)
        else:
            _populate_address(shipment.ShipFrom, shipper_address)

        _populate_address(shipment.ShipTo, request.destination)

        using_ups_pak = False

        paks = []
        for package in request.packages:
            pak = self._RateWS.factory.create('ns2:PackageType')

            pak.Dimensions.UnitOfMeasurement.Code = 'IN'
            pak.Dimensions.Length = str(package.length)
            pak.Dimensions.Width = str(package.width)
            pak.Dimensions.Height = str(package.height)
            pak.PackageWeight.UnitOfMeasurement.Code = 'LBS'
            pak.PackageWeight.Weight = str(package.weight)
            if is_large(package):
                pak.LargePackageIndicator = ''

            if len(package.declarations) > 0 and request.insure:
                _populate_money(
                    pak.PackageServiceOptions.DeclaredValue,
                    package.get_total_declared_value()
                )

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
            pak.PackagingType.Code = '02'

            if pak.PackagingType.Code == '04':  # UPS Pak
                using_ups_pak = True

            paks.append(pak)
        shipment.Package = paks

        if (
            shipment.ShipFrom.Address.CountryCode in ('US', 'PR') and
            request.destination.country.alpha2 not in ('US', 'PR') and
            using_ups_pak
        ):
            # Required if the shipment is from
            # US/PR Outbound to non US/PR
            # destination with the
            # PackagingType of UPS PAK(04)
            raise NotImplementedError()
            shipment.InvoiceLineTotal.CurrencyCode = 'USD'
            shipment.InvoiceLineTotal.MonetaryValue = '0'

        try:
            rates = self._RateWS.service.ProcessRate(
                api_request, _pickup_type, _customer_classification, shipment)
        except WebFault as err:
            _on_webfault(err)

        if rates.Response.ResponseStatus.Code != '1':  # 1 = Success
            raise Exception()

        #if hasattr(rates.Response, 'Alert'):
        #    for alert in rates.Response.Alert:
        #        print 'ALERT:', alert.Description

        return rates

    #def get_service(self, service_id):                                # TODO
    #    return Service(self, service_id, mapping[service_id])

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

        try:
            response = self._XAV.service.ProcessXAV(
                request,
                None,  # missing tag = street-level validation
                2,  # candidate list size
                address_key
            )
        except WebFault as err:
            _on_webfault

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
        #api_request.RequestOption = 'TNT'  # just mimicking the example Perl app
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

        invoice = self._TNTWS.factory.create('ns2:InvoiceLineTotalType')
        _populate_money(invoice, request.get_total_declared_value())

        try:
            response = self._TNTWS.service.ProcessTimeInTransit(
                api_request,
                req_ship_from,
                req_ship_to,
                sticks,
                weight,
                str(len(request.packages)),  # num packages in shipment
                invoice,
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

        except WebFault as err:
            #print err.fault
            print '[[['
            print api_request, ';;'
            print req_ship_from, ';;'
            print req_ship_to, ';;'
            print sticks, ';;'
            print weight, ';;'
            print str(len(request.packages)), ';;'
            print ']]]'
            _on_webfault(err)

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
        rates = self._request_rates(request, 'Rate', service)

        if len(rates.RatedShipment) != 1:
            raise Exception()
        rated_shipment = rates.RatedShipment[0]
        if rated_shipment.Service.Code != service.service_id:
            raise Exception()

        return _get_money(rated_shipment.TotalCharges)


def is_large(package):
    ### http://www.ups.com/content/pr/en/shipping/cost/additional.html#Large+Package+Surcharge
    # A package is considered a "Large Package" when its length plus girth
    # [(2 x width) + (2 x height)] combined exceeds 130 inches, but does not
    # exceed the maximum UPS size of 165 inches.  An Additional Handling Charge
    # will not be assessed when a Large Package Surcharge is applied.

    H, W, L = sorted([package.length, package.width, package.height])
    return L + W * 2 + H * 2 > 130


def _test_is_large():
    from ..data import Package
    assert is_large(Package(10, 10, 91, 0))
    assert not is_large(Package(10, 10, 90, 0))
    assert is_large(Package(91, 10, 10, 0))
    assert is_large(Package(10, 91, 10, 0))
_test_is_large()


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
    if address.postal_code is not None:
        node.Address.PostalCode = address.postal_code.replace(' ', '')
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


def _populate_money(node, value):
    node.CurrencyCode = value.currency
    node.MonetaryValue = str(value.amount)


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

    '01': 'Next Day Air',  # 'UPS Express' if shipping from Canada (delivers before 10:30am) ----- 522 in our DB
    '02': 'Second Day Air',  # 524 in our DB
    # 'UPS Worldwide Expedited' - 02 Rating, 08 Shipping, if shipping from Canada
    '03': 'Ground',  # 523 in our DB
    '07': 'Worldwide Express',  # different names when originating from other countries ----- 520 in our DB
    '08': 'Worldwide Expedited',  # different names when originating from other countries ----- 521 in our DB
    '11': 'Standard',
    '12': 'Three-Day Select',  # 525 in our DB
    '13': 'Next Day Air Saver',  # delivers at 6pm
    '14': 'Next Day Air Early A.M.',  # different name when originating from Canada
    '54': 'Worldwide Express Plus',  # different name when originating from Mexico
    '59': 'Second Day Air A.M.',
    '65': 'Saver',
    '96': 'Worldwide Express Freight'
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
