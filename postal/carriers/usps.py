"""
This is the module for interfacing with FedEx's web services APIs.
"""
import inspect
import logging
import os
from base64 import b64decode
from datetime import datetime
from math import ceil
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
    address_validation = True
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

    @staticmethod
    def _sanity_check(request, origin):
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

    def get_services(self, request):
        origin = request.origin or self.postal_configuration['shipper_address']
        self._sanity_check(request, origin)
        postage_request = self.client.factory.create('PostageRatesRequest')
        package = request.packages[0]
        dims = postage_request.MailpieceDimensions
        dims.Length, dims.Width, dims.Height = sorted(
            [package.length, package.width, package.height])
        postage_request.Machinable = True
        if package.get_total_insured_value() > 0:
            request.Services._InsuredMail = "ON"

        postage_request.InsuredValue = request.get_total_insured_value().amount
        postage_request.FromPostalCode = origin.postal_code
        postage_request.ToPostalCode = request.destination.postal_code
        postage_request.WeightOz = package.weight * 16
        if package.document:
            postage_request.MailpieceShape = 'Flat'
        else:
            postage_request.MailpieceShape = 'Parcel'

        postage_request.RequesterID = self.requester_id
        creds = postage_request.CertifiedIntermediary
        creds.AccountID = self.account_id
        creds.PassPhrase = self.passphrase
        creds.Token = self.token

        if request.destination.country.alpha2 == 'US':
            postage_request.MailClass = 'Domestic'
        else:
            postage_request.MailClass = 'International'
            postage_request.ToCountryCode = request.destination.country.alpha2

        response = self.service_call(
            self.client.service.CalculatePostageRates, postage_request)

        response_dict = self._request_response_table(response)
        self.cache_results(request, response_dict)
        return response_dict