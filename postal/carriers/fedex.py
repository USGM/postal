"""
This is the module for interfacing with FedEx's web services APIs.
"""
from base64 import b64decode
from collections import OrderedDict
from datetime import datetime
from math import ceil
from pprint import pformat
import warnings
from PyPDF2.utils import PdfReadWarning
from dateutil import parser
from decimal import Decimal
from money import Money
from PyPDF2 import PdfFileReader, PdfFileWriter
from suds.client import Client

from .base import Carrier, ClearEmpty, PY3, PostalLogger
from ..exceptions import CarrierError, NotSupportedError, PostalError, \
    AddressError
from ..data import Address, Shipment, Declaration

from io import BytesIO


logger = PostalLogger(carrier_name='FedEx')
warnings.filterwarnings("ignore", category=PdfReadWarning)


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

    # To get FedEx's packaging advantages, you must use their packaging.
    _generic_package_translation = {
        'package': 'YOUR_PACKAGING',
        'envelope': 'YOUR_PACKAGING',
        'softpak': 'YOUR_PACKAGING'}

    # We only apply these translations to envelopes/softpaks. Not to packages,
    # since there are too many options there, and it's too easy to go out of
    # bounds.
    _to_proprietary_packaging = {
        'envelope': 'FEDEX_ENVELOPE',
        'softpak': 'FEDEX_PAK'}

    _package_id_to_description = {
        'FEDEX_10KG_BOX': '10kg Box',
        'FEDEX_25KG_BOX': '25kg Box',
        'FEDEX_BOX': 'Box',
        'FEDEX_ENVELOPE': 'Express Envelope',
        'FEDEX_PAK': 'Pak',
        'FEDEX_TUBE': 'Tube'}

    _min_max_estimates = {
        'FIRST_OVERNIGHT': (1, 1),
        'PRIORITY_OVERNIGHT': (1, 1),
        'STANDARD_OVERNIGHT': (1, 1),
        'FEDEX_2_DAY': (2, 2),
        'FEDEX_2_DAY_AM': (2, 2),
        'FEDEX_EXPRESS_SAVER': (3, 3),
        'FEDEX_GROUND': (1, 5),
        'FEDEX_HOME_DELIVERY': (1, 5),
        'SMART_POST': (2, 14),
        'GROUND_HOME_DELIVERY': (1, 5),
        'SAME_DAY': (0, 0),
        'SAME_DAY_CITY': (0, 0),
        'FEDEX_FIRST_FREIGHT': (1, 1),
        'FEDEX_3_DAY_FREIGHT': (3, 3),
        'INTERNATIONAL_ECONOMY': (4, 6),
        'INTERNATIONAL_ECONOMY_FREIGHT': (4, 6),
        'INTERNATIONAL_PRIORITY_FREIGHT': (1, 3),
        'INTERNATIONAL_FIRST': (1, 8),
        'INTERNATIONAL_PRIORITY': (1, 3),
        'EUROPE_FIRST_INTERNATIONAL_PRIORITY': (1, 1)}

    def create_client(self, wsdl_name):
        client = Client(
            self.service_url(wsdl_name), plugins=[ClearEmpty(), self.log_service],
            timeout=self.postal_configuration.get('timeout', None))
        location = ''
        for service in client.wsdl.services:
            for port in service.ports:
                location = port.location
        if not location:
            raise PostalError("Couldn't load the remote URL for FedEx.")
        if not self.test:
            client.set_options(location=location.replace('beta', ''))
        return client

    def __init__(
            self, key, account_number, password, meter_number, test=True,
            postal_configuration=None):
        super(FedExApi, self).__init__(postal_configuration)
        self.postal_configuration = postal_configuration
        self.key = key
        self.account_number = account_number
        self.password = password
        self.meter_number = meter_number
        self.test = test

        self.rates_client = self.create_client('RateService_v14.wsdl')

        self.address_client = self.create_client('AddressValidationService_v2.wsdl')

        self.ship_client = self.create_client('ShipService_v13.wsdl')

        self.upload_client = self.create_client('UploadDocumentService_v1.wsdl')

        self.tracking_client = self.create_client('TrackService_v12.wsdl')

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
            code = response.Notifications[0].Code

            if code == '521':
                message = ('FedEx requires a valid postal code '
                           'for that region. (If one was '
                           'specified, it is invalid.)')
                err = AddressError(
                    message, fields={'postal_code': message}, code=code)
            elif code == '711':
                message = 'FedEx does not ship to that postal code.'
                err = AddressError(
                    message, fields={'postal_code': message}, code=code)
            else:
                err = CarrierError('Error#%s: %s' % (
                    code, response.Notifications[0].Message), code=code)

            raise err
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
            street_lines=list(
                getattr(addr, 'StreetLines', original.street_lines[:])),
            city=addr.City,
            subdivision=getattr(
                addr, 'StateOrProvinceCode', original.subdivision),
            postal_code=getattr(addr, 'PostalCode', original.postal_code),
            country=getattr(addr, 'CountryCode', original.country.alpha2),
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

        with logger.lock:
            logger.debug_header('Validate Address')
            logger.debug(address)

        result = self.service_call(
            self.address_client.service.addressValidation,
            auth, client_detail, transaction_detail, version_id,
            request_timestamp, address_validation_options, address_item)

        self.log_transmission(self.address_client)

        result = result.AddressResults[0][0][0]
        success = result.Score
        address = self.address_from_validator(result, address)
        with logger.lock:
            logger.debug_header('Response')
            logger.debug(address)
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

    def upload_version_id(self):
        version = self.upload_client.factory.create('VersionId')
        version.ServiceId = 'cdus'
        version.Major = 1
        version.Intermediate = 1
        version.Minor = 0
        return version

    def tracking_version_id(self):
        version = self.tracking_client.factory.create('VersionId')
        version.ServiceId = 'trck'
        version.Major = 12
        version.Intermediate = 0
        version.Minor = 0
        return version

    def label_specification(self, spec):
        spec.LabelFormatType = 'COMMON2D'
        spec.ImageType = 'PDF'
        spec.LabelStockType = 'PAPER_4X6'

    @staticmethod
    def format_label(label):
        # Some jump-around for dual compatibility with Python 2 and 3
        if isinstance(label, bytes):
            label = label.decode('utf-8')
        label = b64decode(label)
        input = PdfFileReader(BytesIO(label))
        input.strict = False
        output = PdfFileWriter()

        page = input.getPage(0)
        page.mediaBox.lowerLeft = (30, 325)
        page.mediaBox.upperRight = (320, 760)
        output.addPage(page)
        output_stream = BytesIO()
        output.write(output_stream)
        return output_stream.getvalue()

    def upload_commercial_invoice(self, request, service):
        origin = self.get_origin(request)
        if not request.international(origin=origin):
            return None
        if request.documents_only() and (
                not service.service_id == 'FEDEX_GROUND'):
            return None
        if not request.all_declarations():
            raise NotSupportedError(
                "This shipment requires Declarations.", code=404)
        invoice = self.commercial_invoice(request)
        if PY3:
            invoice = invoice.encode('utf-8')
        authentication = self.authentication(self.upload_client)
        client = self.user_client(self.upload_client)
        transaction = self.transaction_detail(self.upload_client)
        version = self.upload_version_id()
        document = self.upload_client.factory.create('UploadDocumentDetail')
        document.LineNumber = 1
        document.CustomerReference = 'refId-1'
        document.DocumentType = 'COMMERCIAL_INVOICE'
        document.FileName = 'CommercialInvoice.pdf'
        document.DocumentContent = invoice
        try:
            return self.service_call(
                self.upload_client.service.uploadDocuments, authentication,
                client, transaction, version, origin.country.alpha2,
                request.destination.country.alpha2, [document])
        except CarrierError as err:
            if err.code == '1200':
                raise NotSupportedError(
                    "ETDs aren't supported for either the source or the "
                    "destination country. Please print a commercial invoice "
                    "for this shipment.", code=1200)
            raise err

    def requested_shipment(
            self, service, request, package, sequence_num=None,
            tracking_number=None):
        """
        FedEx supports Multiship, but only one package at a time. They have to
        be 'added' to the initial request with secondary requests.
        """
        self._ensure_supported(request)
        origin = request.origin or self.postal_configuration['shipper_address']

        api_request = self.ship_client.factory.create('RequestedShipment')
        api_request.ShipTimestamp = request.ship_datetime or datetime.now()
        api_request.ServiceType = service.service_id
        api_request.DropoffType = 'REGULAR_PICKUP'
        self.set_saturday_delivery(request, api_request)
        if len(request.packages) == 1:
            api_request.PackagingType = self._get_internal_package_type_code(
                package.package_type, to_proprietary=package.carrier_conversion
            )
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
                [pack.weight for pack in request.packages])
            api_request.TotalWeight.Units = 'LB'
        api_request.PackageCount = len(request.packages)

        self.line_items(
            self.ship_client, request, api_request, [package], sequence_num)

        return api_request

    def set_commercial_invoice(self, invoice, api_request):
        services = api_request.SpecialServicesRequested
        types = services.SpecialServiceTypes or []
        types.append('ELECTRONIC_TRADE_DOCUMENTS')
        services.SpecialServiceTypes = types
        invoice = invoice.DocumentStatuses[0].DocumentId
        reference = self.ship_client.factory.create(
            'UploadDocumentReferenceDetail')
        etd = api_request.SpecialServicesRequested.EtdDetail
        reference.DocumentType = 'COMMERCIAL_INVOICE'
        reference.DocumentId = invoice
        etd.DocumentReferences = [reference]

    @staticmethod
    def set_saturday_delivery(request, api_request):
        if not request.extra_params.get('saturday_delivery', False):
            return
        services = api_request.SpecialServicesRequested
        types = services.SpecialServiceTypes or []
        types.append('SATURDAY_DELIVERY')
        services.SpecialServiceTypes = types

    def ship(self, service, request):
        self._ensure_supported(request)
        auth = self.authentication(self.ship_client)
        client_detail = self.user_client(self.ship_client)
        transaction_detail = self.transaction_detail(self.ship_client)
        version_id = self.ship_version_id()
        package = request.packages[0]
        alerts = []
        requested_shipment = self.requested_shipment(service, request, package)
        invoice = None

        try:
            invoice = self.upload_commercial_invoice(request, service)
        except NotSupportedError as err:
            if err.code == 404:
                raise
            alerts.append(str(err))
        if invoice:
            self.set_commercial_invoice(invoice, requested_shipment)

        with self.logger.lock:
            self.logger.debug_header('Shipment')
            self.logger.debug(service)
            self.logger.debug(request)

        result = self.service_call(
            self.ship_client.service.processShipment, auth, client_detail,
            transaction_detail, version_id, requested_shipment)

        package_details = OrderedDict()
        if len(request.packages) > 1:
            master_tracking_id = (
                result.CompletedShipmentDetail.MasterTrackingId)
        else:
            master_tracking_id = (
                result.CompletedShipmentDetail.CompletedPackageDetails[
                    0].TrackingIds[0])
        detail = result.CompletedShipmentDetail.CompletedPackageDetails[0]
        package_details[package] = {
            'tracking_number': str(master_tracking_id.TrackingNumber),
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
                'tracking_number': str(
                    detail.TrackingIds[0].TrackingNumber),
                'label': self.format_label(detail.Label.Parts[0].Image)}
        tracking_number = str(master_tracking_id.TrackingNumber)

        try:
            rating = result.CompletedShipmentDetail.ShipmentRating
            price = self.get_price_dict(rating, rating.ShipmentRateDetails)
        except (CarrierError, AttributeError):
            raise CarrierError("FedEx returned a nonsense price. Please "
                               "contact their customer service about tracking "
                               "number %s." % tracking_number)
        shipment_dict = {
            'shipment': Shipment(self, tracking_number),
            'packages': package_details,
            'price': price,
            'alerts': alerts}

        with logger.lock:
            logger.debug_header('Response')
            logger.shipment_response(shipment_dict)
        return shipment_dict

    def carrier_codes(self):
        codes = self.rates_client.factory.create('CarrierCodeType')
        return [codes.FDXE, codes.FDXG]

    def line_items(self, client, request, api_request, packages,
                   sequence_num=None):
        commodities = False
        detail = api_request.CustomsClearanceDetail
        for index, package in enumerate(packages):
            item = client.factory.create('RequestedPackageLineItem')
            item.SequenceNumber = sequence_num or index + 1
            item.GroupNumber = 1
            item.GroupPackageCount = 1
            item.Weight.Units.value = 'LB'
            self.sig_handler(request, item)

            # FedEx seems to have an internal error when there are too many
            # decimal digits and it raises a more intelligent error when
            # the weight of a package is zero. But it doesn't have these
            # restrictions for the total weight of the shipment.
            item.Weight.Value = '%.1f' % max(.1, package.weight)

            # Special case for FedEx Envelopes. If the

            if api_request.PackagingType == 'YOUR_PACKAGING':
                dimensions = item.Dimensions
                dimensions.Height = int(ceil(package.height))
                dimensions.Width = int(ceil(package.width))
                dimensions.Length = int(ceil(package.length))
                dimensions.Units = 'IN'

            # FedEx Envelopes are flat rate for wherever they are going. FedEx
            # balks if the envelopes are stated to be over a certain weight,
            # but in practice they don't actually turn them down. Here, we
            # make sure that the weight, if it's under 4 pounds or so, always
            # gets set to .5lbs, to keep us safe.
            if (api_request.PackagingType == 'FEDEX_ENVELOPE') and (
                    package.weight <= 4):
                item.Weight.Value = '0.5'
                api_request.TotalWeight.Value = '0.5'

            if package.declarations or package.documents_only:
                self.set_declarations(client, api_request, package)

                value = package.get_total_insured_value()
                if value > 0:
                    item.InsuredValue.Currency = value.currency
                    item.InsuredValue.Amount = value.amount

            api_request.RequestedPackageLineItems.append(item)
            if package.documents_only:
                detail.DocumentContent = 'DOCUMENTS_ONLY'
                detail.CustomsValue.Currency = (
                    package.get_total_declared_value().currency)
                detail.CustomsValue.Amount = '1.00'
            else:
                commodities = True

        if commodities:
            if request.extra_params.get('fedex_duties_account', False):
                detail.DutiesPayment.PaymentType = 'THIRD_PARTY'
                party = detail.DutiesPayment.Payor.ResponsibleParty
                self.set_address(party, request.extra_params.get(
                    'duties_address', request.destination))
                party.AccountNumber = request.extra_params[
                    'fedex_duties_account']
            else:
                detail.DutiesPayment.PaymentType = 'RECIPIENT'

    @staticmethod
    def set_address(target, address):
        target_address = target.Address
        if len(address.street_lines) > 3:
            raise NotSupportedError(
                "FedEx does not support more than three address lines.")
        if hasattr(target, 'Contact'):
            target.Contact.PersonName = address.contact_name
            target.Contact.PhoneNumber = address.phone_number
        if len(address.street_lines) == 3 and hasattr(target, 'Contact'):
            target.Contact.CompanyName = address.street_lines[0]
            target_address.StreetLines = address.street_lines[1:]
        elif len(address.street_lines) == 3:
            target_address.StreetLines = address.street_lines[1:]
        else:
            target_address.StreetLines = address.street_lines
        target_address.City = address.city
        target_address.PostalCode = address.postal_code
        target_address.CountryCode = address.country.alpha2
        if len(address.subdivision or '') <= 2:
            target_address.StateOrProvinceCode = address.subdivision
        target_address.Residential = address.residential

    def set_declarations(self, client, api_request, package):
        commodities = []
        total_value = 0
        declarations = package.declarations[:]
        if package.documents_only:
            declarations = [
                Declaration(
                    'Printed Documents', Money(
                        '1.00', self.postal_configuration['default_currency']),
                    'US', 1)]

        for declaration in declarations:
            commodity = client.factory.create('Commodity')
            commodity.Description = declaration.description
            value = declaration.value
            commodity.NumberOfPieces = declaration.units
            commodity.UnitPrice.Currency = value.currency
            commodity.UnitPrice.Amount = value.amount
            value *= declaration.units
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
        if not value.Amount:
            value.Amount = 0
        value.Amount += total_value.amount
        value.Currency = total_value.currency

    def requested_shipment_rate(self, request):
        self._ensure_supported(request)
        api_request = self.rates_client.factory.create('RequestedShipment')

        origin = request.origin or self.postal_configuration['shipper_address']
        self.set_address(api_request.Shipper, origin)
        self.set_address(api_request.Recipient, request.destination)
        self.set_saturday_delivery(request, api_request)

        api_request.RateRequestTypes = 'LIST'
        api_request.PackageCount = len(request.packages)
        if len(request.packages) == 1:
            package = request.packages[0]
            api_request.PackagingType = self._get_internal_package_type_code(
                package.package_type, to_proprietary=package.carrier_conversion)
        else:
            api_request.PackagingType = 'YOUR_PACKAGING'

        self.line_items(
            self.rates_client, request, api_request, request.packages)

        api_request.ShipTimestamp = request.ship_datetime

        return api_request

    @staticmethod
    def get_price_dict(info, method_details, retail=False):
        if retail:
            fetch_types = ['PAYOR_LIST_SHIPMENT', 'PAYOR_LIST_PACKAGE']
        else:
            fetch_types = info.ActualRateType  # May raise AttributeError
        price = {}
        for rating in method_details:
            try:
                rating = rating.ShipmentRateDetail
            except AttributeError:
                pass
            if rating.RateType in fetch_types:
                price['total'] = Money(
                    rating.TotalNetCharge.Amount,
                    rating.TotalNetCharge.Currency)
                price['base_price'] = Money(
                    rating.TotalBaseCharge.Amount,
                    rating.TotalBaseCharge.Currency
                )
                if (price['total'] - price['base_price']) < 0:
                    price['base_price'] = price['total']
                    price['fees'] = Money(Decimal('0.0'), 'USD')
                else:
                    price['fees'] = (price['total'] - price['base_price'])
                break
        if not price:
            raise CarrierError("FedEx returned a nonsense price.")
        return price

    # @staticmethod
    def rate_response_dict(self, request, response):
        if not hasattr(response, 'RateReplyDetails'):
            return {}
        return {
            method.ServiceType: {
                'price': FedExApi.get_price_dict(
                    method, method.RatedShipmentDetails, retail=request.extra_params.get('retail_rate'),
                ),
                'delivery_datetime': getattr(
                    method, 'DeliveryTimestamp', None)}
            for method in response.RateReplyDetails}

    @staticmethod
    def sig_handler(request, item):
        sig = request.extra_params.get('signature_required', None)
        if not sig:
            return
        if sig not in ['Direct', 'Adult', 'Indirect']:
            raise NotSupportedError("Signature type not supported: %s." % sig)
        special_services = item.SpecialServicesRequested
        special_services.SpecialServiceTypes = ['SIGNATURE_OPTION']
        special_services.SignatureOptionDetail.OptionType = sig.upper()

    def get_services(self, request):
        """
        Get available services for shipping a package.
        """
        result = self.get_from_cache(request, 'fedex')
        if not result:
            self._ensure_supported(request)
            auth = self.authentication(self.rates_client)
            client = self.user_client(self.rates_client)
            transaction_detail = self.transaction_detail(self.rates_client)
            version = self.rates_version_id()
            return_transit = False
            codes = []
            variable_options = []
            requested_shipment = self.requested_shipment_rate(request)

            with self.logger.lock:
                self.logger.debug_header('Get Services')
                self.logger.debug(request)

            try:
                response = self.service_call(
                    self.rates_client.service.getRates,
                    auth, client, transaction_detail, version, return_transit,
                    codes, variable_options, requested_shipment)
            finally:
                self.log_transmission(self.rates_client)

            result = self.rate_response_dict(request, response)
            self.cache_results(request, result, 'fedex')

        final = {
            self.get_service(key): {
                'price': value['price'],
                'delivery_datetime': value['delivery_datetime'],
                'trackable': True}
            for key, value in result.items()}

        with logger.lock:
            logger.debug_header('Response')
            logger.debug(pformat(final, width=1))

        return final

    def track(self, identifier):
        auth = self.authentication(self.tracking_client)
        client = self.user_client(self.tracking_client)
        transaction_detail = self.transaction_detail(self.tracking_client)
        version = self.tracking_version_id()
        selection_details = self.tracking_client.factory.create('TrackSelectionDetail')
        selection_details.PackageIdentifier.Type = 'TRACKING_NUMBER_OR_DOORTAG'
        selection_details.PackageIdentifier.Value = identifier

        with self.logger.lock:
            self.logger.debug_header('Track number: %s' % identifier)

        try:
            response = self.service_call(
                self.tracking_client.service.track,
                auth, client, transaction_detail, version, selection_details
            )
        finally:
            self.log_transmission(self.rates_client)

        result = {}
        details = response.CompletedTrackDetails[0].TrackDetails[0].StatusDetail

        result['delivered'] = details.Code == 'DL'
        result['finalized'] = details.Code in ['DL', 'CA', 'DE']
        result['status_code'] = u'{}'.format(details.Code)
        result['description'] = u'{}'.format(details.Description)
        street = [' ']

        # Fedex API dose not return StateOrProvinceCode for some countries ex Ghana
        subdivision = False
        if hasattr(details.Location, 'StateOrProvinceCode'):
            subdivision = u'{}'.format(details.Location.StateOrProvinceCode)

        city, country_code = '', ''
        if hasattr(details.Location, 'City'):
            city = details.Location.City
        elif result['delivered'] and hasattr(response.CompletedTrackDetails[0].TrackDetails[0], 'ActualDeliveryAddress'):
            city = response.CompletedTrackDetails[0].TrackDetails[0].ActualDeliveryAddress.City

        if hasattr(details.Location, 'CountryCode'):
            country_code = details.Location.CountryCode
        elif result['delivered'] and hasattr(response.CompletedTrackDetails[0].TrackDetails[0], 'ActualDeliveryAddress'):
            country_code = response.CompletedTrackDetails[0].TrackDetails[0].ActualDeliveryAddress.CountryCode

        result['location'] = Address(
            street_lines=street,
            city=u'{}'.format(city),
            subdivision=subdivision,
            country=u'{}'.format(country_code),
        )

        if hasattr(details, 'CreationTime'):
            result['event_time'] = details.CreationTime
        elif hasattr(response.CompletedTrackDetails[0].TrackDetails[0], 'Events'):
            events = response.CompletedTrackDetails[0].TrackDetails[0].Events
            event = events.pop()
            result['event_time'] = event.Timestamp
        return result

    def delivery_datetime(self, service, request):
        self._ensure_supported(request)
        data = self.get_from_cache(request, 'fedex')
        if not data:
            self.get_services(request)
        data = self.get_from_cache(request, 'fedex').get(service.service_id, None)
        if not data:
            raise NotSupportedError(
                "FedEx does not support shipment of that package on this service."
            )
        return data['delivery_datetime']

    def quote(self, service, request):
        self._ensure_supported(request)
        data = self.get_from_cache(request, 'fedex')
        if not data:
            self.get_services(request)
        data = self.get_from_cache(request, 'fedex').get(service.service_id, None)
        if not data:
            raise NotSupportedError(
                "FedEx does not support shipment of that package on this service.")
        return data['price']

    def _ensure_supported(self, request):
        if request.destination.subdivision and \
                len(request.destination.subdivision) > 3:
            raise NotSupportedError(
                'FedEx requires the use of ISO_3166-2 state/province codes, '
                'not names.')

# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [FedExApi]
