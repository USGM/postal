"""
This is the module for interfacing with USPS via the Endicia Lable Server API.

Multiship is supported but in a peculiar way. Because USPS does not support
multiship directly, it must be faked by chaining transactions. As a group of
these transactions is not atomic, it is possible to have a request return a
shipment dictionary where some of the packages were processed and others
weren't. These packages can then be retried.

Packages that fail will have neither a tracking number nor a label when
returned.

It was considered that an exception could be raised when this happened, but to
do so would mean that some packages would have been shipped, and others would
not have. Automatically refunding the packages would also be problematic, as
the cause of the original problem might also prevent the refund working.
"""
from base64 import b64decode
from datetime import datetime
from dateutil.relativedelta import relativedelta
from math import ceil
import random
import re
from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from suds.client import Client
from money import Money

from base import Carrier, ClearEmpty
from ..exceptions import CarrierError, NotSupportedError
from ..data import Shipment, sigfig


class USPSApi(Carrier):
    """
    Implements calls to the FedEx web API.
    """
    name = 'USPS'
    address_validation = False
    _code_to_description = {
        'PriorityExpress': 'Priority Mail Express',
        'First': 'First-Class Mail',
        'StandardPost': 'Standard Post',
        'Priority': 'Priority Mail',
        'CriticalMail': 'Critical Mail',
        'PriorityMailExpressInternational': 'Priority Mail Express '
                                            'International',
        'ExpressMailInternational': 'Priority Mail Express International',
        'FirstClassMailInternational': 'First-Class Mail International',
        'FirstClassPackageInternationalService': 'First Class Package '
                                                 'International Service',
        'PriorityMailInternational': 'Priority Mail International'}

    _generic_package_translation = {
        'envelope': 'Flat',
        'softpak': 'Parcel',
        'package': 'Parcel'}

    _to_proprietary_packaging = {
        'envelope': 'FlatRateEnvelope',
        'softpak': 'FlatRatePaddedEnvelope'}

    _package_id_to_description = {
        'Letter': 'Generic Letter',
        'Flat': 'Generic Flat',
        'FlatRateEnvelope': 'Flat Rate Envelope',
        'FlatRateLegalEnvelope': 'Flat Rate Legal Envelope',
        'FlatRatePaddedEnvelope': 'Flate Rate Padded Envelope',
        'SmallFlatRateEnvelope': ' Small Flat Rate Envelope',
        'SmallFlatRateBox': 'Small Flat Rate Box',
        'MediumFlatRateBox': 'Medium Flat Rate Box',
        'LargeFlatRateBox': 'Large Flat Rate Box',
        'Parcel': 'Generic Package'}

    # Needed when figuring out what label to print.
    _parcel_types = (
        'softpak', 'SmallFlatRateBox', 'MediumFlatRateBox', 'LargeFlatRateBox',
        'Parcel')

    def __init__(
            self, account_id, passphrase, requester_id, test=True,
            postal_configuration=None):
        super(USPSApi, self).__init__(postal_configuration)
        self.account_id = account_id
        self.passphrase = passphrase
        self.requester_id = requester_id
        self.postal_configuration = postal_configuration

        if test:
            url = 'https://www.envmgr.com/LabelService/EwsLabelService.' \
                  'asmx?WSDL'
        else:
            url = 'https://labelserver.endicia.com/LabelService/' \
                  'EwsLabelService.asmx?WSDL'

        self.client = Client(url, plugins=[ClearEmpty()])

    def service_call(self, func, *args, **kwargs):
        response = super(USPSApi, self).service_call(func, *args, **kwargs)
        try:
            if response.Status != 0:
                raise CarrierError(response.ErrorMessage)
        except AttributeError:
            pass
        return response

    def _sanity_check(self, request):
        origin = self.get_origin(request)
        if origin.country.alpha2 != 'US':
            raise NotSupportedError(
                "USPS only ships from the United States.")

    @staticmethod
    def _service_day(proposed_datetime):
        """
        This doesn't catch all holidays, but will stop it from displaying a few
        and Sundays.
        """
        # Sundays
        if proposed_datetime.weekday == 6:
            return False
        # Christmas and New Years Eve
        if proposed_datetime.month == 12 and proposed_datetime.day in [
                24, 25, 31]:
            return False
        # New Years Day
        if proposed_datetime.month == 1 and proposed_datetime.day == 1:
            return False
        # Veterans Day
        if proposed_datetime.month == 11 and proposed_datetime.day == 11:
            return False
        # Independence day
        if proposed_datetime.month == 7 and proposed_datetime.day == 4:
            return False

        return True

    @classmethod
    def _get_arrival_date(cls, request, days):
        if not days:
            return None
        date = request.ship_datetime or datetime.now()
        # Any day up to the delivery day could be a holiday.
        for delta in range(0, days + 1):
            date += relativedelta(days=delta)
            while not cls._service_day(date):
                date += relativedelta(days=1)
        return date

    def _request_response_table(self, request, response):
        table = {}
        try:
            response.PostagePrice
        except AttributeError:
            return table
        for rate in response.PostagePrice:
            if not rate.MailClass in self._code_to_description:
                continue
            service = self.get_service(rate.MailClass)
            table[service] = {
                'price': Money(rate._TotalAmount, 'USD'),
                'delivery_datetime': self._get_arrival_date(
                    request, int(rate.DeliveryTimeDays)),
                'trackable': self.is_trackable(request, service)}
        return table

    def _set_dims(self, api_request, package):
        dims = api_request.MailpieceDimensions
        dims.Length, dims.Width, dims.Height = sorted(
            [sigfig(package.length), sigfig(package.width),
                sigfig(package.height)])
        ounces = int(ceil(package.weight * 16))
        if not ounces:
            ounces = 1
        api_request.WeightOz = ounces
        api_request.Machinable = True
        package_type = self.package_type_translate(
            package.package_type, proprietary=package.carrier_conversion).code
        if package_type == 'softpak':
            api_request.PackageTypeIndicator = 'Softpak'
            api_request.MailPieceShape = 'Package'
        else:
            api_request.MailpieceShape = package_type

    def _set_creds(self, api_request, inset=False):
        api_request.RequesterID = self.requester_id
        if inset:
            creds = api_request.CertifiedIntermediary
        else:
            creds = api_request
        creds.AccountID = self.account_id
        creds.PassPhrase = self.passphrase

    @staticmethod
    def _insurance_params(api_request, package):
        if package.get_total_insured_value() > 0:
            api_request.Services._InsuredMail = "ENDICIA"
        api_request.InsuredValue = package.get_total_insured_value().amount

    @staticmethod
    def _format_phone(phone_number):
        phone_number = re.sub('[^\d]', '', phone_number)
        if phone_number[0] == '1':
            phone_number = phone_number[1:]
        phone_number = phone_number[:10]
        if len(phone_number) != 10:
            raise NotSupportedError(
                'USPS requires a standard US 10 digit phone number.')
        return phone_number

    @staticmethod
    def _set_lines(api_request, lines, prefix):
        for index, line in enumerate(lines):
            line_num = index + 1
            if line_num > 3:
                raise NotSupportedError(
                    "USPS cannot take more than 4 address lines.")
            setattr(api_request, '%sAddress%s' % (prefix, line_num), line)

    def _set_address_info(self, api_request, request, short=False):
        origin = self.get_origin(request)
        api_request.FromPostalCode = origin.postal_code
        api_request.ToPostalCode = request.destination.postal_code
        if request.international(origin) and short:
            api_request.MailClass = 'International'
            api_request.ToCountryCode = request.destination.country.alpha2
        elif short:
            api_request.MailClass = 'Domestic'
        if short:
            return
        if origin.subdivision:
            from_state = origin.subdivision.upper()
        else:
            from_state = None

        if request.destination.subdivision:
            to_state = request.destination.subdivision.upper()
        else:
            to_state = None

        api_request.FromName = origin.contact_name
        api_request.FromState = from_state
        api_request.FromCity = origin.city
        api_request.FromPhone = self._format_phone(origin.phone_number)
        api_request.ToName = request.destination.contact_name
        api_request.ToState = to_state
        api_request.ToCity = request.destination.city
        api_request.ToCountryCode = request.destination.country.alpha2
        self._set_lines(api_request, origin.street_lines, 'Return')
        self._set_lines(api_request, request.destination.street_lines, 'To')

    @staticmethod
    def ref_number():
        """
        Generate reference number for request.
        """
        return str(random.randrange(
            1000000000000000000000000, 9999999999999999999999999))

    @staticmethod
    def _format_label(label, type):
        input = PdfFileReader(StringIO(b64decode(label)))
        output = PdfFileWriter()

        page = input.getPage(0)
        if type == 'Domestic':
            page.mediaBox.lowerLeft = (162.3, 324.3)
            page.mediaBox.upperRight = (450, 756)
        elif type == 'FORM2976':
            page.mediaBox.lowerLeft = (90, 468)
            page.mediaBox.upperRight = (521, 752)

        output.addPage(page)
        output_stream = StringIO()
        output.write(output_stream)

        return output_stream.getvalue()

    def _merge_labels(self, labels):
        output = PdfFileWriter()
        pages = []
        for label in labels:
            input = PdfFileReader(StringIO(label))
            pages.append(input.getPage(0))
        for page in pages:
            output.addPage(page)
        output_stream = StringIO()
        output.write(output_stream)
        return output_stream.getvalue()

    def _label_type(self, request, service, package):
        origin = self.get_origin(request)
        package_type = self.package_type_translate(
            package.package_type, proprietary=package.carrier_conversion).code
        if package_type not in self._parcel_types:
            package_type = 'Flat'
        else:
            package_type = 'Parcel'
        if not request.international(origin):
            return 'Domestic'
        if service.service_id in [
                'FirstClassMailInternational',
                'FirstClassPackageInternationalService']:
            return 'FORM2976'
        if (service.service_id == 'PriorityMailInternational') and (
                package_type == 'Parcel'):
            return 'FORM2976A'
        elif (service.service_id == 'PriorityMailInternational') and (
                package_type == 'Flat'):
            return 'FORM2976'
        elif service.service_id == 'PriorityMailExpressInternational':
            return 'FORM2976A'
        return 'FORM2976A'

    def is_trackable(self, request, service):
        """
        Some services don't have real tracking numbers, but Endicia likes to
        pretend they do.
        """
        if service.service_id in [
            'First', 'FirstClassMailInternational',
                'FirstClassPackageInternationalService']:
            return False
        if not request.international(self.get_origin(request)):
            return True
        package_types = [
            self.package_type_translate(
                package.package_type, proprietary=package.carrier_conversion
            ).code for package in request.packages]

        for package_type in package_types:
            if package_type in ['FlatRateEnvelope', 'FlatRateLegalEnvelope',
                            'FlatRatePaddedEnvelope', 'SmallFlatRateEnvelope',
                            'SmallFlatRateBox', 'MediumFlatRateBox',
                            'LargeFlatRateBox']:
                return False
        return True

    def ship_package(self, request, service, package):
        label_request = self.client.factory.create('LabelRequest')
        label_request.MailClass = service.service_id
        label_request.PartnerTransactionID = self.ref_number()
        self._set_dims(label_request, package)
        self._insurance_params(label_request, package)
        self._set_creds(label_request)
        self._set_address_info(label_request, request)
        label_request._ImageFormat = 'PDF'
        label_format = self._label_type(request, service, package)
        label_request.Stealth = 'TRUE'
        if request.international(origin=self.get_origin(request)):
            label_request._LabelType = 'International'
            label_request._LabelSubtype = 'Integrated'
            label_request.IntegratedFormType = label_format

        for declaration in package.declarations:
            item = self.client.factory.create('CustomsItem')
            item.Quantity = declaration.units
            if str(declaration.value.currency) != 'USD':
                raise NotSupportedError(
                    "All declarations must be in US Dollars for USPS.")
            item.Value = declaration.value.amount
            item.CountryOfOrigin = declaration.origin_country.alpha2
            item.Description = declaration.description
            item.Weight = int(ceil(
                float(package.weight) / len(package.declarations) /
                declaration.units))
            label_request.CustomsInfo.CustomsItems.CustomsItem.append(item)
            if request.documents_only():
                label_request.CustomsInfo.ContentsType = 'Documents'
            else:
                label_request.CustomsInfo.ContentsType = self.get_param(
                    request, 'contents', 'Gift')
        response = self.service_call(
            self.client.service.GetPostageLabel, label_request)
        if hasattr(response, 'TrackingNumber'):
            tracking_number = response.TrackingNumber
        else:
            tracking_number = ''
        if not tracking_number and not hasattr(response, 'PIC'):
            raise CarrierError(response.ErrorMessage)
        transaction_id = None
        if hasattr(response, 'PIC'):
            transaction_id = response.PIC
        transaction_id = transaction_id or tracking_number
        if not self.is_trackable(request, service):
            tracking_number = 'N/A'
        shipment = Shipment(
            self, tracking_number, transaction_id=transaction_id)
        price = Money(response.FinalPostage, 'USD')
        try:
            label = self._format_label(response.Base64LabelImage, label_format)
        except AttributeError:
            images = []
            for image in response.Label.Image:
                images.append(self._format_label(image.value, label_format))
            label = self._merge_labels(images)
        return {
            'shipment': shipment,
            'price': price,
            'packages': {
                package: {
                    'tracking_number': tracking_number,
                    'label': label}}}

    def compile_shipments(self, response_list):
        packages_source = [response['packages'] for response in response_list]
        packages = {}
        for pack in packages_source:
            packages.update(pack)
        shipments = [
            response['shipment'].transaction_id for response in response_list
            if 'shipment' in response]
        price = sum(response['price'] for response in response_list
                    if 'price' in response)
        shipment = Shipment(
            self, 'N/A', transaction_id=':'.join(shipments))
        if not shipment.transaction_id:
            raise CarrierError("All packages failed to make it through.")
        return {'shipment': shipment, 'price': price, 'packages': packages}

    def ship(self, service, request):
        self._sanity_check(request)
        # Too dangerous to allow multiship if any packages don't work. So we
        # force a rate check before doing anything else. This should raise
        # an exception if there's a problem with any of the packages.
        self.quote(service, request)
        responses = []
        if len(request.packages) == 1:
            return self.ship_package(request, service, request.packages[0])
        for package in request.packages:
            try:
                responses.append(self.ship_package(request, service, package))
            except CarrierError as err:
                # One of the packages didn't ship correctly.
                responses.append({
                    'packages': {package: {
                        'label': None, 'tracking_number': None}}})
        return self.compile_shipments(responses)

    def refill(self, dollar_amount):
        """
        Required for any software to be certified with Endicia-- recharge the
        user's Endicia balance.
        """
        refill_request = self.client.factory.create('RecreditRequest')
        refill_request.RequestID = self.ref_number()
        self._set_creds(refill_request, inset=True)
        refill_request.RecreditAmount = dollar_amount.amount
        self.client.service.BuyPostage(refill_request)

    def change_passphrase(self, new_passphrase):
        """
        Required for any software to be certfied with Endicia-- change the
        passphrase on the account.

        Note: This will NOT update your configuration files. It will, however,
        be applied immediately to this instance of the USPSApi.
        """
        change_request = self.client.factory.create('ChangePassPhraseRequest')
        self._set_creds(change_request, inset=True)
        change_request.RequestID = self.ref_number()
        change_request.NewPassPhrase = new_passphrase
        response = self.service_call(
            self.client.service.ChangePassPhrase, change_request)
        if response.Status != 0:
            raise CarrierError(
                unicode(response.ErrorMessage).encode(encoding='utf-8'))
        self.passphrase = new_passphrase

    def compile_options(self, request, response_list):
        service_sets = [
            {service for service in response.keys()}
            for response in response_list]
        # Get services that can work on all packages.
        try:
            services = set.intersection(*service_sets)
        except TypeError:
            return {}
        final_response = {}
        for service in services:
            price = sum(
                [response[service]['price'] for response in response_list])
            # The latest delivery date will be our estimate.
            datetimes = []
            trackable = self.is_trackable(request, service)
            for response in response_list:
                delivery = response[service]['delivery_datetime']
                if delivery is not None:
                    datetimes.append(delivery)
                trackable = response[service]['trackable']
            if not datetimes:
                delivery_datetime = None
            else:
                delivery_datetime = max(datetimes)
            final_response[service] = {
                'price': price, 'delivery_datetime': delivery_datetime,
                'trackable': trackable}
        return final_response

    def get_services(self, request):
        self._sanity_check(request)
        responses = []
        for package in request.packages:
            postage_request = self.client.factory.create('PostageRatesRequest')
            self._set_dims(postage_request, package)
            self._set_address_info(postage_request, request, short=True)
            self._set_creds(postage_request, inset=True)
            self._insurance_params(postage_request, package)
            postage_request.DeliveryTimeDays = "TRUE"
            response = self.service_call(
                self.client.service.CalculatePostageRates, postage_request)
            response_dict = self._request_response_table(request, response)
            responses.append(response_dict)
        responses = self.compile_options(request, responses)
        self.cache_results(request, responses)
        return responses

    def delivery_datetime(self, service, request):
        response = self.get_services(request)
        try:
            return response[service]['delivery_datetime']
        except KeyError:
            raise NotSupportedError(
                "USPS does not support shipment of that package on "
                "this service.")

    def quote(self, service, request):
        response = self.get_services(request)
        try:
            return response[service]['price']
        except KeyError:
            raise NotSupportedError(
                "USPS does not support shipment of that package on "
                "this service.")