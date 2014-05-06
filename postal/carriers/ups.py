from collections import OrderedDict
import inspect
from math import ceil
import os
import base64
from pprint import pformat
import sys

from Queue import Queue
from threading import Thread

from datetime import datetime
from io import BytesIO

import PIL.Image
from .base import Carrier, PostalLogger
import suds.cache

try:
    import money
except ImportError:
    import Money as money

from suds.client import Client
from suds.plugin import MessagePlugin
from suds.sax.element import Element
from suds import WebFault

from ..data import Address, Shipment
from ..exceptions import CarrierError, NotSupportedError, AddressError

__author__ = 'Nathan Everitt'


logger = PostalLogger(carrier_name='UPS')


class FixBrokenNamespace(MessagePlugin):
    def __init__(self, propname, schema):
        self.schema = schema
        self.propname = propname

    def swap_namespaces(self, namespace, tags):
        for tag in tags:
            children = tag.getChildren()
            if children:
                self.swap_namespaces(namespace, children)
            tag.prefix = namespace

    def get_namespace(self, context):
        declarations = context.envelope.nsdeclarations().split()
        for dec in declarations:
            if self.schema in dec:
                return dec.split(':')[1].split('=')[0]
        raise CarrierError("Could not find namespace schema.")

    def marshalled(self, context):
        namespace = self.get_namespace(context)
        self.swap_namespaces(
            namespace,
            [context.envelope.getChild('Body').getChild(
                self.propname).getChild('Request')])


class FixMissingNegotiatedRates(FixBrokenNamespace):

    def marshalled(self, context):
        shipment_rating_options = Element('ShipmentRatingOptions')
        negotiated_rates_indicator = Element('NegotiatedRatesIndicator')
        shipment_rating_options.append(negotiated_rates_indicator)

        namespace = self.get_namespace(context)
        context.envelope.getChild('Body').getChild(self.propname).getChild(
            'Shipment').append(shipment_rating_options)
        self.swap_namespaces(namespace, [shipment_rating_options])


class FixInternationalNamespaces(MessagePlugin):
    def marshalled(self, context):
        request = context.envelope.getChild('Body').getChild('ShipmentRequest')
        options = request.getChild(
            'Shipment').getChild('ShipmentServiceOptions')
        rating_options = request.getChild('Shipment').getChild(
            'ShipmentRatingOptions')

        if options:
            rating_options.prefix = 'ns2'
            rating_options.getChild('NegotiatedRatesIndicator').prefix = 'ns2'


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


class UPSApi(Carrier):

    # Used when generating some ambiguous SOAP objects.
    common = 'http://www.ups.com/XMLSchema/XOLTWS/Common/v1.0'
    common_pfx = '{%s}' % common
    shipment = "http://www.ups.com/XMLSchema/XOLTWS/Ship/v1.0"
    rates = "http://www.ups.com/XMLSchema/XOLTWS/Rate/v1.1"

    name = 'UPS'
    address_validation = True
    auto_residential = True
    _code_to_description = {

        # 'UPS Express' if shipping from Canada
        # (delivers before 10:30am)
        '01': 'Next Day Air',

        # 524 in our DB
        '02': 'Second Day Air',

        # 'UPS Worldwide Expedited' - 02 Rating, 08 Shipping,
        # if shipping from Canada

        '03': 'Ground',

        # different names when originating from other countries
        '07': 'Worldwide Express',

        # different names when originating from other countries
        '08': 'Worldwide Expedited',
        '11': 'Standard',
        '12': 'Three-Day Select',
        '13': 'Next Day Air Saver',

        # different name when originating from Canada
        '14': 'Next Day Air Early A.M.',

        # different name when originating from Mexico
        '54': 'Worldwide Express Plus',

        '59': 'Second Day Air A.M.',
        '65': 'Saver',
        '96': 'Worldwide Express Freight'}

    _to_proprietary_packaging = {
        'softpak': '04',
        'envelope': '01'}

    _generic_package_translation = {
        'package': '02',
        'softpak': '02',
        'envelope': '02'}

    _package_id_to_description = {
        '01': 'Express Envelope',
        '03': 'Tube',
        '04': 'Pak',  # proprietary softpak, not generic
        '21': 'Express Box',
        '24': '25kg Box',
        '25': '10kg Box',
        '30': 'Pallet',
        '2a': 'Small Express Box',
        '2b': 'Medium Express Box',
        '2c': 'Large Express Box'
        ### For FRS rating requests the
        ### only valid value is customer
        ### supplied packaging 02.
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
        #?: 'G'  # UPS Ground ---- Puerto Rico to United States and
        # United States to Puerto Rico
    }

    _min_max_estimates = {
        '01': (1, 1),  # Next Day Air
        '02': (2, 2),  # Second Day Air
        '03': (1, 5),  # Ground
        '07': (1, 3),  # Worldwide Express
        '08': (2, 5),  # Worldwide Expedited

        ### '11' (Standard) depends on day of shipment request

        '12': (3, 3),  # Three-Day Select
        '13': (1, 1),  # Next Day Air Saver
        '14': (1, 1),  # Next Day Air Early AM
        '54': (1, 3),  # Worldwide Express Plus
        '59': (2, 2),  # Second Day Air AM

        '65': (1, 3),  # Saver ------ it's 1-3 for international and undocumented for domestic

        '96': (1, 3),  # Worldwide Express Freight
    }

    @staticmethod
    def _get_directory_of(frame):
        return os.path.split((os.path.abspath(inspect.getfile(frame))))[0]

    @classmethod
    def _get_path(cls, name):
        return 'file://' + os.path.join(
            cls._get_directory_of(inspect.currentframe()),
            'wsdl', 'ups', name)

    def _create_client(self, name, plugins=None):
        if not plugins:
            plugins = []
        client = Client(
            self._get_path(name),
            cache=suds.cache.NoCache(),
            plugins=plugins,
            timeout=self.postal_configuration.get('timeout', None))
        return client

    def __init__(
            self, username, password, access_license_number, shipper_number,
            test, auto_time_in_transit=True, postal_configuration=None):
        super(UPSApi, self).__init__(postal_configuration)
        self.shipper_number = shipper_number
        self.auto_time_in_transit = auto_time_in_transit

        authentication = AuthenticationPlugin(
            username, password, access_license_number)

        self._RateWS = self._create_client(
            'RateWS.wsdl',
            plugins=[
                authentication, FixBrokenNamespace('RateRequest', self.common),
                FixMissingNegotiatedRates('RateRequest', self.rates)])

        self._XAV = self._create_client(
            'XAV.wsdl',
            plugins=[authentication, FixBrokenNamespace(
                'XAVRequest', self.common)])

        self._TNTWS = self._create_client(
            'TNTWS.wsdl',
            plugins=[
                authentication, FixBrokenNamespace(
                    'TimeInTransitRequest', self.common)])

        self._Ship = self._create_client(
            'Ship.wsdl',
            plugins=[
                authentication, FixBrokenNamespace(
                    'ShipmentRequest', self.common),
                FixMissingNegotiatedRates('ShipmentRequest', self.shipment),
                FixInternationalNamespaces()])

        if not test:
            self._Ship.set_options(
                location='https://onlinetools.ups.com/webservices/Ship')

    @staticmethod
    def _convert_webfault(webfault):
        error = webfault.fault.detail.Errors.ErrorDetail.PrimaryErrorCode

        code = error.Code
        if code == '111210':
            result = NotSupportedError('UPS does not offer that service to '
                                       'that destination. (Double-check your '
                                       'address.)', code=code)
        elif code == '270005':
            message = ('UPS requires a valid postal code for that region. '
                       '(If one was specified, it is invalid.)')
            result = AddressError(
                message, fields={'postal_code': message}, code=code)
        elif code == '270040':  # "City is ambiguous"
            # Once had this problem with an address where the city was
            # correct but the postal code was wrong. Because UPS.
            result = AddressError(
                'City is ambiguous. If it should not be, double check the '
                'postal code.', fields={
                    'city': 'City may be ambiguous.',
                    'postal_code': 'If the city is not ambiguous, check to '
                                   'make sure this postal code is for this '
                                   'city.'})

        elif code == '111285':
            result = AddressError(
                'UPS has no rates for that address. '
                'The postal code/city/country may be incorrect.',
                fields={'postal_code': 'Please double-check the postal code.'},
                code=code)
        elif code == '111286':
            result = NotSupportedError(
                'UPS has no rates for that address.',
                fields={
                    'subdivision': 'The state/province may be incorrect.'},
                code=code)
        elif code == '121211':
            # Got this error for the Adult Signature Only option, though it
            # probably applies to the other ShipmentServiceOptions
            result = NotSupportedError('UPS does not support that accessory '
                                       'option to that address.', code=code)
        elif code == '120802':
            result = NotSupportedError('UPS does not recognize that as a '
                                       'valid destination address.', code=code)
        else:
            logger.error('UPS: Webfault#%s: %s'
                         % (error.Code, error.Description))
            result = CarrierError('Webfault#%s: %s'
                                  % (error.Code, error.Description), code=code)

        return result

    @staticmethod
    def _on_unknown_error():
        logger.error('UPS: Unknown error.')
        raise CarrierError('UPS encountered an unknown error.')

    @classmethod
    def _get_negotiated_charge(cls, rated_shipment):
        if hasattr(rated_shipment, 'NegotiatedRateCharges'):
            return cls._get_money(
                rated_shipment.NegotiatedRateCharges.TotalCharge)
        else:
            logger.debug('UPS: No negotiated rates given.')
            return cls._get_money(rated_shipment.TotalCharges)

    @staticmethod
    def get_length_plus_girth(package):
        height, width, length = sorted(
            [package.length, package.width, package.height])
        return length + width * 2 + height * 2

    @staticmethod
    def _populate_address(
            node, address, use_street=True,
            use_name=True, use_phone=False, use_attn=False,
            international=False):
        """
        node = shipment.Shipper|shipment.ShipFrom|shipment.ShipTo
        """

        if address.contact_name:
            if len(address.contact_name) > 35:
                raise NotSupportedError(
                    'UPS requires the contact name to be at most 35 '
                    'characters long. The company name should be in the '
                    'street lines.')
            if use_name:
                node.Name = address.contact_name
            if use_attn:
                node.AttentionName = address.contact_name

        if address.street_lines:
            if len(address.street_lines) > 3:
                raise NotSupportedError('UPS does not support more than three '
                                        'address lines.')
            for line in address.street_lines:
                if len(line) > 35:
                    raise NotSupportedError(
                        'UPS requires each address line to be at most 35 '
                        'characters long.')
                if use_street:
                    node.Address.AddressLine = address.street_lines

        node.Address.City = address.city
        if address.subdivision:
            node.Address.StateProvinceCode = address.subdivision.upper()
        if address.postal_code is not None:
            node.Address.PostalCode = address.postal_code.replace(' ', '')
        node.Address.CountryCode = address.country.alpha2
        if not international and address.residential:
            node.Address.ResidentialAddressIndicator = ''
        if use_phone:
            node.Phone.Number = address.phone_number

    @classmethod
    def _populate_shipper(
            cls, node, address, shipper_number, use_attn=False,
            use_phone=False,tax_identification_number=None):
        cls._populate_address(
            node, address, use_phone=use_phone, use_attn=use_attn)
        node.ShipperNumber = shipper_number

        if tax_identification_number is not None:
            node.TaxIdentificationNumber = tax_identification_number

    @staticmethod
    def _get_money(node):
        return money.Money(node.MonetaryValue, node.CurrencyCode)

    @staticmethod
    def _populate_money(node, value, whole_number=False):
        node.CurrencyCode = value.currency
        if not whole_number:
            node.MonetaryValue = str(value.amount)
        else:
            node.MonetaryValue = int(ceil(value.amount))

    @classmethod
    def is_large(cls, package):
        """
        A package is considered a "Large Package" when its length plus girth
        [(2 x width) + (2 x height)] combined exceeds 130 inches, but does
        not exceed the maximum UPS size of 165 inches.  An Additional
        Handling Charge will not be assessed when a Large Package
        Surcharge is applied.
        """
        if package.package_type.code in ['01', 'envelope']:
            return False
        return cls.get_length_plus_girth(package) > 130

    @classmethod
    def _ensure_request_supported(cls, request):
        for package in request.packages:
            cls._ensure_package_supported(package)

    @classmethod
    def _ensure_package_supported(cls, package):
        if package.package_type.code not in ['01', 'envelope']:
            if cls.get_length_plus_girth(package) > 165:
                raise NotSupportedError('UPS does not ship packages of '
                                        'that size.')
        if package.weight > 150:
            raise NotSupportedError('UPS does not ship packages that weigh '
                                    'more than 150 pounds.')

    def ship(self, service, request, receiver_account_number=None):
        self._ensure_request_supported(request)

        origin = request.origin or self.postal_configuration['shipper_address']
        international = (origin.country != request.destination.country)

        api_request = self._Ship.factory.create(
            '%sRequestType' % self.common_pfx)
        api_request.RequestOption = 'validate'

        api_shipment = self._Ship.factory.create('ns3:ShipmentType')

        if international and request.documents_only():
            api_shipment.DocumentsOnlyIndicator = ''

        api_shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = ''
        api_shipment.Service.Code = service.service_id

        ### Other destinations require the invoice line total to be set in
        ### one of the international tags.
        ### From an email: this amount is not used as a declared value and does
        ### not affect shipment charges. This is also true of any associated
        ### amounts within the International Forms container.
        if request.destination.country.alpha2 in ('CA', 'PR'):
            self._populate_money(
                api_shipment.InvoiceLineTotal,
                request.get_total_declared_value())

        self._populate_shipper(
            api_shipment.Shipper, origin, self.shipper_number,
            True, True, self.postal_configuration['tax_id'])

        self._populate_address(
            api_shipment.ShipTo, request.destination, use_phone=True,
            use_attn=True, use_name=True, international=international)

        self._populate_address(
            api_shipment.ShipFrom, origin, use_phone=True,
            use_attn=True, international=international)

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

        api_package = []
        api_product = []

        for package in request.packages:
            pak = self._Ship.factory.create('ns3:PackageType')
            self._populate_package(pak, package)

            api_package.append(pak)

            if international:
                if not package.declarations:
                    if package.documents_only:
                        product = self._Ship.factory.create('ns2:ProductType')
                        product.Description = ['documents']
                        product.Unit.Number = 1
                        product.Unit.UnitOfMeasurement.Code = 'PCS'  # pieces
                        product.Unit.Value = 1
                        product.OriginCountryCode = origin.country.alpha2

                        api_product.append(product)
                    else:
                        raise NotSupportedError('UPS requires each package '
                                                "in an international shipment "
                                                "that isn't documents only to "
                                                'have declarations.')
                else:
                    for dec in package.declarations:
                        product = self._Ship.factory.create('ns2:ProductType')
                        product.Description = [dec.description]
                        product.Unit.Number = dec.units
                        product.Unit.UnitOfMeasurement.Code = 'PCS'  # pieces
                        product.Unit.Value = dec.value.amount
                        product.OriginCountryCode = dec.origin_country.alpha2

                        api_product.append(product)

        api_shipment.Package = api_package

        if international:
            bill_receiver = self._Ship.factory.create('ns3:ShipmentChargeType')
            bill_receiver.Type = '02'

            ### Evidently, if this is blank, UPS will contact the receiver
            ### in order to acquire billing information.
            bill_receiver.BillReceiver.AccountNumber = receiver_account_number

            form = api_shipment.ShipmentServiceOptions.InternationalForms
            form.FormType = '01'
            form.CurrencyCode = request.get_total_insured_value().currency
            form.InvoiceDate = datetime.now().strftime('%Y%m%d')

            form.Product = api_product

            # TODO: Should eventually be parameterized
            form.ReasonForExport = 'GIFT'

            self._populate_address(
                form.Contacts.SoldTo,
                request.destination, use_phone=True, use_attn=True,
                international=True)

            descriptions = []
            for pack in request.packages:
                if pack.declarations:
                    for dec in pack.declarations:
                        descriptions.append(dec.description)
                elif pack.documents_only:
                    descriptions.append('documents')
                else:
                    raise NotSupportedError('UPS requires each package '
                                            "in an international shipment "
                                            "that isn't documents only to "
                                            'have declarations.')
            description = ', '.join(descriptions)

            ### UPS does not allow descriptions longer than 50 characters.
            api_shipment.Description = description[0:50]

        ### signature requirement upon receipt
        # Valid values are: 1 -
        # Delivery Confirmation
        # Signature Required 2 -
        # Delivery Confirmation
        # Adult Signature
        # Required. Forwards
        # Only
        signature_required = request.extra_params.get(
            'signature_required', None)
        if signature_required:
            confirm = api_shipment.ShipmentServiceOptions.DeliveryConfirmation
            if signature_required == 'Adult':
                confirm.DCISType = 2
            elif signature_required == 'Indirect':
                confirm.DCISType = 1
            else:
                raise NotSupportedError('UPS does not support that signature '
                                        'confirmation method - only indirect '
                                        'and adult-only.')

        label_spec = self._Ship.factory.create('ns3:LabelSpecificationType')
        label_spec.LabelImageFormat.Code = 'GIF'

        receipt_spec = self._Ship.factory.create(
            'ns3:ReceiptSpecificationType')

        with logger.lock:
            logger.debug_header('Shipment')
            logger.debug(service)
            logger.debug(request)
        try:
            response = self._Ship.service.ProcessShipment(
                api_request, api_shipment, label_spec, receipt_spec)
            logger.sent(self._Ship.last_sent())
            logger.sent(self._Ship.last_received())
        except WebFault as err:
            logger.sent(self._Ship.last_sent())
            logger.received(self._Ship.last_received())
            raise self._convert_webfault(err)
        finally:
            with logger.lock:
                logger.debug(self._Ship.last_sent())
                logger.debug(self._Ship.last_received())

        negotiated_rate = self._get_money(
            response.ShipmentResults.NegotiatedRateCharges.TotalCharge)

        if response.Response.ResponseStatus.Code != '1':
            self._on_unknown_error()

        master_tracking_number = \
            response.ShipmentResults.ShipmentIdentificationNumber

        packages = OrderedDict()

        for index, pak in enumerate(response.ShipmentResults.PackageResults):
            pdf = BytesIO()
            label = pak.ShippingLabel.GraphicImage
            if isinstance(label, bytes):
                label = label.decode('utf-8')
            label = base64.b64decode(label)
            image = BytesIO(label)
            image = PIL.Image.open(image)
            image = image.transpose(PIL.Image.ROTATE_270)
            image = image.crop((0, 0, 800, 1200))
            image.save(pdf, 'PDF', resolution=200)

            packages[request.packages[index]] = {
                'tracking_number': pak.TrackingNumber,
                'label': pdf.getvalue()}

        result = {'shipment': Shipment(self, master_tracking_number),
                  'packages': packages,
                  'price': negotiated_rate}

        with logger.lock:
            logger.debug_header('Response')
            logger.shipment_response(result)

        return result

    def _task(self, request, rated_shipment, shipment_info):
        """
        Because the delivery datetime check must be done on a separate web
        request, we break this down into tasks so the requests run in parallel.
        """
        try:
            service = self.get_service(rated_shipment.Service.Code)

            info = {'price': self._get_negotiated_charge(rated_shipment),
                    'alerts': [a.Description
                               for a in rated_shipment.RatedShipmentAlert],
                    'trackable': True}

            if self.auto_time_in_transit:
                info['delivery_datetime'] = self.delivery_datetime(service, request)
            else:
                info['delivery_datetime'] = None

            shipment_info.put((service, info))

        except Exception as err:
            err.traceback = sys.exc_info()[2]
            shipment_info.put(err)

    def get_services(self, request):
        self._ensure_request_supported(request)

        with logger.lock:
            logger.debug_header('Get Services')
            logger.debug(request)
        rates = self._request_rates(request, 'Shop')

        shipment_info = Queue()
        # Each request takes multiple web service calls.
        # We thread for efficiency.
        for rated_shipment in rates.RatedShipment:
            thread = Thread(target=self._task,
                            args=(request, rated_shipment, shipment_info))
            thread.start()
            
        result = {}
        for _ in rates.RatedShipment:
            info = shipment_info.get()
            if isinstance(info, Exception):
                raise info
            else:
                service, rates = info
                result[service] = rates

        with logger.lock:
            logger.debug_header('Response')
            logger.debug(pformat(result, width=1))
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
        """
        self._ensure_request_supported(request)

        DAILY_PICKUP = '01'
        SHIPPER = '00'

        api_request = self._RateWS.factory.create(
            '%sRequestType' % self.common_pfx)
        api_request.RequestOption = [request_type]

        _pickup_type = self._RateWS.factory.create('ns2:CodeDescriptionType')
        _pickup_type.Code = DAILY_PICKUP

        _customer_classification = self._RateWS.factory.create(
            'ns2:CodeDescriptionType')
        _customer_classification.Code = SHIPPER

        shipment = self._RateWS.factory.create('ns2:ShipmentType')
        shipment.ShipmentRatingOptions.NegotiatedRatesIndicator = ''

        if request.documents_only():
            shipment.DocumentsOnlyIndicator = ''

        if request_type == 'Rate' and service is None:
            raise TypeError()
        if request_type == 'Shop' and service is not None:
            raise TypeError()

        if service is not None:
            shipment.Service.Code = service.service_id
            shipment.Service.Description = service.name

        origin = request.origin or self.postal_configuration['shipper_address']

        self._populate_shipper(
            shipment.Shipper, origin, self.shipper_number)
        self._populate_address(shipment.ShipFrom, origin)
        self._populate_address(shipment.ShipTo, request.destination)

        paks = []
        for package in request.packages:
            pak = self._RateWS.factory.create('ns2:PackageType')
            self._populate_package(pak, package)
            paks.append(pak)
        shipment.Package = paks

        try:
            rates = self._RateWS.service.ProcessRate(
                api_request, _pickup_type, _customer_classification, shipment)
        except WebFault as err:
            raise self._convert_webfault(err)

        # 1 = Success
        if rates.Response.ResponseStatus.Code != '1':
            self._on_unknown_error()

        return rates

    def validate_address(self, address):
        request = self._XAV.factory.create('%sRequestType' % self.common_pfx)
        request.RequestOption = '3'  # validation and classification

        address_key = self._XAV.factory.create('ns2:AddressKeyFormatType')
        address_key.ConsigneeName = address.contact_name
        address_key.AddressLine = address.street_lines[0]
        address_key.PoliticalDivision2 = address.city
        address_key.PoliticalDivision1 = address.subdivision
        address_key.CountryCode = address.country.alpha2
        address_key.PostcodePrimaryLow = address.postal_code

        with logger.lock:
            logger.debug_header('Validate Address')
            logger.debug(address)
        try:
            response = self._XAV.service.ProcessXAV(
                request,
                None,  # missing tag = street-level validation
                1,  # candidate list size
                address_key)

        except WebFault as err:
            raise self._convert_webfault(err)

        if response.Response.ResponseStatus.Code != '1':
            self._on_unknown_error()

        if not hasattr(response, 'Candidate') or len(response.Candidate) == 0:
            with logger.lock:
                logger.debug_header('Response')
                logger.debug('Invalid')
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

        lines = candidate.AddressKeyFormat.AddressLine
        if hasattr(candidate.AddressKeyFormat, 'Urbanization'):
            lines.append(candidate.AddressKeyFormat.Urbanization)

        result = Address(
            contact_name=address.contact_name,
            phone_number=address.phone_number,
            street_lines=lines,
            subdivision=candidate.AddressKeyFormat.PoliticalDivision1,
            city=candidate.AddressKeyFormat.PoliticalDivision2,
            postal_code=postal_code,
            country=candidate.AddressKeyFormat.CountryCode,
            residential=residential)

        if result == address:
            with logger.lock:
                logger.debug_header('Response')
                logger.debug('Valid')
            return True, result
        else:
            with logger.lock:
                logger.debug_header('Response')
                logger.debug('Corrected to:')
                logger.debug(result)
            return False, result

    def delivery_datetime(self, service, request):
        self._ensure_request_supported(request)

        api_request = self._TNTWS.factory.create(
            '%sRequestType' % self.common_pfx)

        # Does not seem to matter what its
        # contents are as long as this tag is not missing.
        api_request.RequestOption = ''

        origin = request.origin or self.postal_configuration['shipper_address']
        international = (origin.country != request.destination.country)

        req_ship_from = self._TNTWS.factory.create('ns2:RequestShipFromType')
        self._populate_address(
            req_ship_from, origin, use_street=False, use_name=False)

        req_ship_to = self._TNTWS.factory.create('ns2:RequestShipToType')
        self._populate_address(
            req_ship_to, request.destination, use_street=False, use_name=False)

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

        ### UPS's TiT API won't take a weight that is zero
        weight.Weight = str(request.total_weight() or .1)

        invoice = self._TNTWS.factory.create('ns2:InvoiceLineTotalType')
        self._populate_money(
            invoice, request.get_total_declared_value(), whole_number=True)

        if international and request.documents_only():
            documents = ''  # empty tag = true
        else:
            documents = None  # missing tag = false

        bill_type, max_list, sat_morn, drop_off, hold_pickup = (
            None, None, None, None, None)

        num_packages = len(request.packages)

        with logger.lock:
            logger.debug_header('Time in Transit')
            logger.debug(service)
            logger.debug(request)
        try:
            response = self._TNTWS.service.ProcessTimeInTransit(
                api_request, req_ship_from, req_ship_to, sticks, weight,
                num_packages, invoice, documents, bill_type, max_list,
                sat_morn, drop_off, hold_pickup)

        except WebFault as err:
            code = err.fault.detail.Errors.ErrorDetail.PrimaryErrorCode.Code
            if code == '270037':  # no TiT information available
                with logger.lock:
                    logger.debug_header('Response')
                    logger.debug('No TiT information available.')
                return None
            elif code == '270019':  # TiT service is not available
                with logger.lock:
                    logger.debug_header('Response')
                    logger.warning('TiT service is not available.')
                return None  # It's not essential information
            raise self._convert_webfault(err)

        if response.Response.ResponseStatus.Code != '1':
            self._on_unknown_error()

        if not hasattr(response, 'TransitResponse'):
            # a warning because UPS is being inconsistent for unknown reasons
            with logger.lock:
                logger.debug_header('Response')
                logger.warning('No TiT information given.')
                logger.warning(response)
            return None

        for summary in response.TransitResponse.ServiceSummary:
            if (summary.Service.Code !=
                    self._service_code_to_time_in_transit_code[
                        service.service_id]):
                continue

            date = summary.EstimatedArrival.Arrival.Date
            time = summary.EstimatedArrival.Arrival.Time
            result = datetime(
                year=int(date[0:4]),
                month=int(date[4:6]),
                day=int(date[6:8]),
                hour=int(time[0:2]),
                minute=int(time[2:4]))
            with logger.lock:
                logger.debug_header('Response')
                logger.debug(result)
            return result

        with logger.lock:
            logger.debug_header('Response')
            logger.warning('No matching TiT info found.')
            logger.warning(response)
        return None

    def quote(self, service, request):
        self._ensure_request_supported(request)

        with logger.lock:
            logger.debug_header('Get Price')
            logger.debug(service)
            logger.debug(request)
        rates = self._request_rates(request, 'Rate', service)

        if len(rates.RatedShipment) != 1:
            with logger.lock:
                logger.debug_header('Response')
                logger.debug('No rates available.')
                logger.debug(rates)
            raise CarrierError('UPS has no rates available for those '
                               'parameters.')
        rated_shipment = rates.RatedShipment[0]
        if rated_shipment.Service.Code != service.service_id:
            with logger.lock:
                logger.debug_header('Response')
                logger.debug('No rates available.')
                logger.debug(rates)
            raise CarrierError('UPS has no rates available for those '
                               'parameters.')

        result = self._get_negotiated_charge(rated_shipment)

        with logger.lock:
            logger.debug_header('Response')
            logger.debug(result)

        return result

    def _populate_package(self, api_package, package):
        packaging_code = self._get_internal_package_type_code(
            package.package_type, to_proprietary=package.carrier_conversion)

        try:
            api_package.Packaging.Code = packaging_code  # shipping
        except AttributeError:
            api_package.PackagingType.Code = packaging_code  # rating

        dims = api_package.Dimensions
        if packaging_code != '01':  # UPS Letter
            dims.UnitOfMeasurement.Code = 'IN'

            ### Specify too many decimal digits here and it says that
            ### "every dimension is required and must be > zero".
            ### Seriously, UPS?
            dims.Length = '%.2f' % max(1, package.length)
            dims.Width = '%.2f' % max(1, package.width)
            dims.Height = '%.2f' % max(1, package.height)

        api_package.PackageWeight.UnitOfMeasurement.Code = 'LBS'

        api_package.PackageWeight.Weight = '%.1f' % max(.1, package.weight)

        if self.is_large(package):
            # Make sure this tag shows up.
            api_package.LargePackageIndicator = ''

        self._populate_money(
            api_package.PackageServiceOptions.DeclaredValue,
            package.get_total_insured_value())

        if package.get_total_insured_value() > 0:  # for rates
            # can't treat Money instance as boolean
            self._populate_money(
                api_package.PackageServiceOptions.DeclaredValue,
                package.get_total_insured_value())

        return api_package