import inspect
import os
import base64
import threading
from Queue import Queue
import traceback
import sys

from datetime import datetime
from StringIO import StringIO

import PIL.Image
import suds.cache
import money
import base

from suds.client import Client
from suds.plugin import MessagePlugin
from suds.sax.element import Element
from suds import WebFault

from ..data import Address, Shipment
from ..exceptions import CarrierError

__author__ = 'Nathan Everitt'


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


class FixMissingShipmentNegotiatedRates(MessagePlugin):
    def marshalled(self, context):
        shipment_rating_options = Element('ShipmentRatingOptions')
        shipment_rating_options.prefix = 'ns1'
        negotiated_rates_indicator = Element('NegotiatedRatesIndicator')
        negotiated_rates_indicator.prefix = 'ns1'

        context.envelope.getChild('Body').getChild('ShipmentRequest').getChild('Shipment').append(
            shipment_rating_options)
        shipment_rating_options.append(negotiated_rates_indicator)


class FixMissingRatesNegotiatedRates(MessagePlugin):
    def marshalled(self, context):
        shipment_rating_options = Element('ShipmentRatingOptions')
        shipment_rating_options.prefix = 'ns1'
        negotiated_rates_indicator = Element('NegotiatedRatesIndicator')
        negotiated_rates_indicator.prefix = 'ns1'

        context.envelope.getChild('Body').getChild('RateRequest').getChild('Shipment').append(
            shipment_rating_options)
        shipment_rating_options.append(negotiated_rates_indicator)


class AuthenticationPlugin(MessagePlugin):
    def __init__(self, username, password, access_license_number):
        self.username = username
        self.password = password
        self.access_license_number = access_license_number

    def marshalled(self, context):
        header = context.envelope.getChild('Header')

        security = Element('upss:UPSSecurity')
        security.set(
            'xmlns:upss', "http://www.ups.com/XMLSchema/XOLTWS/UPSS/v1.0")

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
        get_directory_of(inspect.currentframe()), 'wsdl', 'ups', 'Void.wsdl'),
    cache=suds.cache.NoCache())


def _on_webfault(webfault):
    error = webfault.fault.detail.Errors.ErrorDetail.PrimaryErrorCode
    return CarrierError(
        'Webfault#%s:%s' % (error.Code, error.Description))


class UPSApi(base.Carrier):
    name = 'UPS'
    address_validation = True
    auto_residential = True

    def __init__(
            self, username, password, access_license_number, shipper_number,
            postal_configuration=None):
        super(UPSApi, self).__init__(postal_configuration)
        self.shipper_number = shipper_number

        authentication = AuthenticationPlugin(
            username, password, access_license_number)

        self._RateWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'RateWS.wsdl'),
            plugins=[
                authentication, FixBrokenRateNamespace(),
                FixMissingRatesNegotiatedRates()
            ],
            timeout=postal_configuration['timeout'])
        self._XAV = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'XAV.wsdl'),
            plugins=[authentication, FixBrokenAddressNamespace()],
            timeout=postal_configuration['timeout'])
        self._TNTWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'TNTWS.wsdl'),
            plugins=[authentication, FixBrokenTimeNamespace()],
            timeout=postal_configuration['timeout'])
        self._Ship = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'Ship.wsdl'),
            cache=suds.cache.NoCache(),
            plugins=[
                authentication, FixBrokenShipmentRequestNamespace(),
                FixMissingShipmentNegotiatedRates()
            ],
            timeout=postal_configuration['timeout'])
        self.TNTWS = Client(
            'file://' + os.path.join(
                get_directory_of(inspect.currentframe()),
                'wsdl', 'ups', 'TNTWS.wsdl'),
            cache=suds.cache.NoCache(),
            plugins=[
                AuthenticationPlugin(
                    username, password, access_license_number),
                FixBrokenTimeNamespace()],
            timeout=postal_configuration['timeout'])

    def ship(self, service, request, receiver_account_number=None):
        origin = request.origin or self.postal_configuration['shipper_address']

        api_request = self._Ship.factory.create('ns0:RequestType')
        api_request.RequestOption = 'validate'

        api_shipment = self._Ship.factory.create('ns3:ShipmentType')
        api_shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = ''
        api_shipment.Service.Code = service.service_id

        _populate_shipper(
            api_shipment.Shipper, origin, self.shipper_number,
            True, True, '123456')
        _populate_address(
            api_shipment.ShipTo, request.destination, use_phone=True,
            use_attn=True)

        _populate_address(
            api_shipment.ShipFrom, request.origin, use_phone=True,
            use_attn=True)

        international = (origin.country != request.destination.country)

        shipper_charge = self._Ship.factory.create('ns3:ShipmentChargeType')
        api_shipment.PaymentInformation.ShipmentCharge = [shipper_charge]

        # A shipment charge type of 01 means Transportation is required.
        #
        # A shipment charge type of 02 means Duties and Taxes are not
        # required; however, this charge type is invalid for Qualified Domestic
        # Shipments. A Qualified Domestic Shipment is any shipment in which
        # one of the following applies:
        #
        # 1) The origin and destination country
        # is the same
        # 2) US to PR shipment
        # 3) PR to USshipment
        # 4) The origin and destination country are both European Union
        # Countries and the GoodsNotInFreeCirculation indicator is not
        # present
        # 5) The origin and destination IATA code is the same

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

            if ((len(package.declarations) > 0 and request.insure)
                    or international):
                _populate_money(
                    pak.PackageServiceOptions.DeclaredValue,
                    package.get_total_declared_value())
            return pak

        api_shipment.Package = [
            package_to_package_type(a) for a in request.packages]


        description = ', '.join([
            a.description

            ### flatten list of lists of declarations
            for a in sum([b.declarations for b in request.packages], [])])

        # UPS does not allow descriptions greater than 50 characters.
        api_shipment.Description = description[0:50]

        label_spec = self._Ship.factory.create('ns3:LabelSpecificationType')
        label_spec.LabelImageFormat.Code = 'GIF'

        receipt_spec = self._Ship.factory.create(
            'ns3:ReceiptSpecificationType')

        try:
            response = self._Ship.service.ProcessShipment(
                api_request, api_shipment, label_spec, receipt_spec)
        except WebFault as err:
            raise _on_webfault(err)

        published_rate = _get_money(
            response.ShipmentResults.ShipmentCharges.TotalCharges)
        negotiated_rate = _get_money(
            response.ShipmentResults.NegotiatedRateCharges.TotalCharge)
        ### TODO: store/return these rates ^

        if response.Response.ResponseStatus.Code != '1':
            raise CarrierError(
                "UPS returned an unknown failure, and did not raise a"
                " webfault.")

        master_tracking_number = \
            response.ShipmentResults.ShipmentIdentificationNumber

        packages = {}

        for index, pak in enumerate(response.ShipmentResults.PackageResults):
            pdf = StringIO()
            image = StringIO(base64.b64decode(pak.ShippingLabel.GraphicImage))
            image = PIL.Image.open(image)
            image = image.transpose(PIL.Image.ROTATE_270)
            image = image.crop((0, 0, 800, 1200))
            image.save(pdf, 'PDF', resolution=200)

            packages[request.packages[index]] = {
                'tracking_number': pak.TrackingNumber,
                'label': pdf.getvalue()}

        return Shipment(self, master_tracking_number, packages)

    def get_services(self, request):
        rates = self._request_rates(request, 'Shop')

        shipment_info = Queue()
        for rated_shipment in rates.RatedShipment:
            def task(rated_shipment):
                try:
                    service = base.Service(
                        self,
                        rated_shipment.Service.Code,
                        _service_code_to_description.get(
                            rated_shipment.Service.Code, None))

                    shipment_info.put((service, dict(
                        price=_get_money(rated_shipment.TotalCharges),
                        delivery_datetime=self.delivery_datetime(
                            service, request),
                        alerts=[a.Description
                            for a in rated_shipment.RatedShipmentAlert]
                    )))
                except Exception as err:
                    err.traceback = sys.exc_info()[2]
                    shipment_info.put(err)

            threading.Thread(target=task, args=(rated_shipment,)).start()
            
        result = {}
        for i in range(len(rates.RatedShipment)):
            a = shipment_info.get()
            if isinstance(a, Exception):
                print str(type(a)) + ': ' + str(a)
                traceback.print_tb(a.traceback)
                raise a
            else:
                service, rates = a
                result[service] = rates
        return result

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

        origin = request.origin or self.postal_configuration['shipper_address']

        _populate_shipper(
            shipment.Shipper, origin, self.shipper_number)

        _populate_address(shipment.ShipFrom, origin)

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
                    package.get_total_declared_value())

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

        if (shipment.ShipFrom.Address.CountryCode in ('US', 'PR') and
                request.destination.country.alpha2 not in ('US', 'PR') and
                using_ups_pak):
            # Required if the shipment is from
            # US/PR Outbound to non US/PR
            # destination with the
            # PackagingType of UPS PAK(04)
            raise NotImplementedError()
            #shipment.InvoiceLineTotal.CurrencyCode = 'USD'
            #shipment.InvoiceLineTotal.MonetaryValue = '0'

        try:
            rates = self._RateWS.service.ProcessRate(
                api_request, _pickup_type, _customer_classification, shipment)
        except WebFault as err:
            raise _on_webfault(err)

        if rates.Response.ResponseStatus.Code != '1':  # 1 = Success
            raise Exception()

        #if hasattr(rates.Response, 'Alert'):
        #    for alert in rates.Response.Alert:
        #        print 'ALERT:', alert.Description

        return rates

    #def get_service(self, service_id):                                # TODO
    #    return Service(self, service_id, mapping[service_id])

    def validate_address(self, address):
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

                # missing tag = street-level validation
                None,

                # candidate list size
                2,

                address_key)

        except WebFault as err:
            raise _on_webfault(err)

        if response.Response.ResponseStatus.Code != '1':
            raise Exception()

        if not hasattr(response, 'Candidate') or len(response.Candidate) == 0:
            return False, address

        candidate = response.Candidate[0]

        residential = candidate.AddressClassification.Code
        # 0 means UPS isn't sure. Default to original spec.
        table = {'0': address.residential, '1': False, '2': True}
        residential = table[residential]

        address_key = candidate.AddressKeyFormat
        postal_code = address_key.PostcodePrimaryLow
        if address_key.PostcodeExtendedLow:
            postal_code += '-%s' % address_key.PostcodeExtendedLow

        result = Address(
            contact_name=address.contact_name,
            phone_number=address.phone_number,
            street_lines=candidate.AddressKeyFormat.AddressLine,
            subdivision=candidate.AddressKeyFormat.PoliticalDivision1,
            city=candidate.AddressKeyFormat.PoliticalDivision2,
            postal_code=postal_code,
            country=candidate.AddressKeyFormat.CountryCode,
            residential=residential,
            urbanization=(
                candidate.AddressKeyFormat.Urbanization
                if hasattr(candidate.AddressKeyFormat, 'Urbanization') else
                None))

        if result == address:
            return True, result
        else:
            return False, result

    def delivery_datetime(self, service, request):
        api_request = self._TNTWS.factory.create('ns0:RequestType')

        # Does not seem to matter what its
        # contents are as long as the tag is not missing.
        api_request.RequestOption = ''

        origin = request.origin or self.postal_configuration['shipper_address']

        req_ship_from = self._TNTWS.factory.create('ns2:RequestShipFromType')
        _populate_address(
            req_ship_from, origin,
            urbanization_title='Town', use_street=False, use_name=False)

        req_ship_to = self._TNTWS.factory.create('ns2:RequestShipToType')
        _populate_address(
            req_ship_to, request.destination,
            urbanization_title='Town', use_street=False, use_name=False)

        sticks = self._TNTWS.factory.create('ns2:PickupType')
        ship_datetime = request.ship_datetime
        if request.ship_datetime is None:
            ship_datetime = datetime.now()
        # YYYYMMDD
        sticks.Date = ship_datetime.strftime('%Y%m%d')

        ### HHMM
        sticks.Time = ship_datetime.strftime('%H%M')

        weight = self._TNTWS.factory.create('ns2:ShipmentWeightType')
        weight.UnitOfMeasurement.Code = 'LBS'

        weight.Weight = str(
            sum([package.weight for package in request.packages]))

        invoice = self._TNTWS.factory.create('ns2:InvoiceLineTotalType')
        _populate_money(invoice, request.get_total_declared_value())

        try:
            response = self._TNTWS.service.ProcessTimeInTransit(
                api_request,
                req_ship_from,
                req_ship_to,
                sticks,
                weight,

                # num packages in shipment
                str(len(request.packages)),
                invoice,
                # DocumentsOnlyIndicator (missing tag = false)
                None,

                # BillType
                # This field needs to be populated when UPS WorldWide
                # Express Freight Shipment Service is needed to be returned in
                # response. The valid value is 04.
                None,

                # MaximumListSize - default is 35
                None,

                # SaturdayDeliveryInfoRequestIndicator
                # missing tag = no
                None,

                # DropOffAtFacilityIndicator
                # missing tag = pick up at warehouse
                None,

                # HoldForPickupIndicator
                # If present, indicates pickup by consignee. If absent,
                # indicates delivery by UPS. This accessorial is valid
                # if Bill Type is 04.
                None)

        except WebFault as err:
            raise _on_webfault(err)

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

        ### If no negotiated rates:
        #return _get_money(rated_shipment.TotalCharges)

        ### otherwise:
        return _get_money(rated_shipment.NegotiatedRateCharges.TotalCharge)


def is_large(package):
    ### http://www.ups.com/content/pr/en/shipping/cost/additional.html#Large+Package+Surcharge
    # A package is considered a "Large Package" when its length plus girth
    # [(2 x width) + (2 x height)] combined exceeds 130 inches, but does not
    # exceed the maximum UPS size of 165 inches.  An Additional Handling Charge
    # will not be assessed when a Large Package Surcharge is applied.

    height, width, length = sorted(
        [package.length, package.width, package.height])
    return length + width * 2 + height * 2 > 130


def _test_is_large():
    from ..data import Package
    assert is_large(Package(10, 10, 91, 0))
    assert not is_large(Package(10, 10, 90, 0))
    assert is_large(Package(91, 10, 10, 0))
    assert is_large(Package(10, 91, 10, 0))
_test_is_large()


def _populate_address(
        node, address, urbanization_title='Urbanization', use_street=True,
        use_name=True, use_phone=False, use_attn=False):
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
        tax_identification_number=None):
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
