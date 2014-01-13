"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import logging
import os
from base64 import b64decode
from datetime import datetime
from math import ceil
import random
import re
from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from suds.client import Client
from money import Money
from suds.plugin import DocumentPlugin

from base import Carrier, Service, ClearEmpty
from ..exceptions import CarrierError, NotSupportedError
from ..data import Address, Shipment


class USPSApi(Carrier):
    """
    Implements calls to the FedEx web API.
    """
    name = 'USPS'
    address_validation = False
    multiship = False
    _code_to_description = {
        'PriorityExpress': 'Priority Mail Express',
        'First': 'First-Class Mail',
        'StandardPost': 'Standard Post',
        'Priority': 'Priority Mail',
        'CriticalMail': 'Critical Mail',
        'PriorityMailExpressInternational': 'Priority Mail Express '
                                            'International',
        'FirstClassMailInternational': 'First-Class Mail International',
        'FirstClassPackageInternationalService': 'First Class Package '
                                                 'International Service',
        'PriorityMailInternational': 'Priority Mail International'}

    def __init__(
            self, account_id, passphrase, requester_id, token,
            postal_configuration=None):
        super(USPSApi, self).__init__(postal_configuration)
        self.account_id = account_id
        self.passphrase = passphrase
        self.requester_id = requester_id
        self.token = token
        self.postal_configuration = postal_configuration

        self.client = Client(
            'https://www.envmgr.com/LabelService/EwsLabelService.asmx?WSDL',
            plugins=[ClearEmpty()])

    def _sanity_check(self, request):
        origin = self.get_origin(request)
        if len(request.packages) != 1:
            raise NotSupportedError(
                "USPS will only accept requests with one"
                " parcel, not %s" % len(request.packages))
        if origin.country.alpha2 != 'US':
            raise NotSupportedError(
                "The USPS only ships from the United States.")

    def _request_response_table(self, response):
        table = {}
        try:
            response.PostagePrice
        except AttributeError:
            return {}
        for rate in response.PostagePrice:
            if not rate.MailClass in self._code_to_description:
                continue
            service = self.create_service(rate.MailClass)
            table[service] = {
                'price': Money(rate._TotalAmount, 'USD'),
                'delivery_datetime': None}
        return table

    def _set_dims(self, api_request, package):
        dims = api_request.MailpieceDimensions
        dims.Length, dims.Width, dims.Height = sorted(
            [package.length, package.width, package.height])
        api_request.WeightOz = package.weight * 16
        api_request.Machinable = True
        if package.document:
            api_request.MailpieceShape = 'Flat'
        else:
            api_request.MailpieceShape = 'Parcel'

    def _set_creds(self, api_request, subset=False):
        api_request.RequesterID = self.requester_id
        if subset:
            creds = api_request.CertifiedIntermediary
        else:
            creds = api_request
        creds.AccountID = self.account_id
        creds.PassPhrase = self.passphrase
        creds.Token = self.token

    @staticmethod
    def _insurance_params(api_request, package):
        if package.get_total_insured_value() > 0:
            api_request.Services._InsuredMail = "ON"
        api_request.InsuredValue = package.get_total_insured_value().amount

    @staticmethod
    def _format_phone(phone_number):
        phone_number = re.sub('[^\d]', '', phone_number)
        if phone_number[0] == '1':
            phone_number = phone_number[1:]
        phone_number = phone_number[:10]
        if len(phone_number) != 10:
            raise NotSupportedError(
                'Phone number for USPS must be a standard US 10 digit number.')
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
        api_request.FromName = origin.contact_name
        api_request.FromState = origin.subdivision
        api_request.FromCity = origin.city
        api_request.FromPhone = self._format_phone(origin.phone_number)
        api_request.ToName = request.destination.contact_name
        api_request.ToState = request.destination.subdivision
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
    def _format_label(label, international=False):
        input = PdfFileReader(StringIO(b64decode(label)))
        output = PdfFileWriter()

        page = input.getPage(0)
        if international:
            page.mediaBox.lowerLeft = (18, 360)
            page.mediaBox.upperRight = (594, 756)
        else:
            page.mediaBox.lowerLeft = (162.3, 324.3)
            page.mediaBox.upperRight = (450, 756)
        output.addPage(page)
        output_stream = StringIO()
        output.write(output_stream)
        return output_stream.getvalue()

    def ship(self, service, request):
        self._sanity_check(request)
        label_request = self.client.factory.create('LabelRequest')
        label_request.MailClass = service.service_id
        label_request.PartnerTransactionID = self.ref_number()
        package = request.packages[0]
        self._set_dims(label_request, package)
        self._insurance_params(label_request, package)
        self._set_creds(label_request)
        self._set_address_info(label_request, request)
        label_request._ImageFormat = 'PDF'
        if request.international():
            label_request._LabelType = 'International'
            label_request._LabelSubtype = 'Integrated'
            label_request.IntegratedFormType = 'FORM2976A'

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
            label_request.CustomsInfo.ContentsType = self.get_param(
                request, 'contents', 'Gift')
        response = self.service_call(
            self.client.service.GetPostageLabel, label_request)
        if response.Status != 0:
            raise CarrierError(response.ErrorMessage)
        if hasattr(response, 'TrackingNumber'):
            tracking_number = response.TrackingNumber
        else:
            tracking_number = None
        shipment = Shipment(self, tracking_number)
        price = Money(response.FinalPostage, 'USD')
        try:
            label = self._format_label(response.Base64LabelImage)
        except AttributeError:
            label = self._format_label(
                response.Label.Image[0].value, international=True)

        return {
            'shipment': shipment,
            'price': price,
            'packages': {
                package: {
                    'tracking_number': tracking_number,
                    'label': label}}}

    def get_services(self, request):
        self._sanity_check(request)
        postage_request = self.client.factory.create('PostageRatesRequest')
        package = request.packages[0]
        self._set_dims(postage_request, package)
        self._set_address_info(postage_request, request, short=True)
        self._set_creds(postage_request, subset=True)
        self._insurance_params(postage_request, package)

        response = self.service_call(
            self.client.service.CalculatePostageRates, postage_request)

        response_dict = self._request_response_table(response)
        self.cache_results(request, response_dict)
        return response_dict