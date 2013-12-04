"""
This is the module for interfacing with DHL's web services APIs.

DHL has declined to provide a WSDL file for their web services. While they do
provide XSL files which could be used to generate Python classes to manipulate,
the result is a workflow that is still too unfavorable in the cost/benefit
department.

So, instead, we use a set of templates and populate these to make the final
request.
"""
import inspect
import os
from base64 import b64decode
from datetime import datetime
from math import ceil
from xml.etree.ElementTree import tostring, fromstring, ElementTree

from PyPDF2 import PdfFileReader, PdfFileWriter
from StringIO import StringIO
from money import Money
from requests import post, RequestException

from base import Carrier, Service, ClearEmpty
from templates.dhl.build import (
    create_header, enumerate_pieces, money_snippet, rates_request)
from ..exceptions import ExceedsLimitsError, CarrierError
from ..data import Address, Shipment


class DHLApi(Carrier):
    name = 'DHL'

    def __init__(self, site_id, password, test_mode=False):
        super(DHLApi, self).__init__()
        self.site_id = site_id
        self.password = password

        self.request_header = create_header(site_id, password)

        if test_mode:
            self.url = 'https://xmlpitest-ea.dhl.com/XMLShippingServlet'
        else:
            self.url = 'https://xmlpi-ea.dhl.com/XMLShippingServlet'

    def make_call(self, call):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = post(self.url, data=call, headers=headers)
            response.raise_for_status()
        except RequestException as err:
            raise CarrierError("%s" % err)
        root = fromstring(response.text)
        content = root[0][1]
        condition = content.find('Condition')
        if content.tag in ['Note', 'Status'] and (condition is not None):
            raise CarrierError("Error %s. %s" % (
                condition.findtext('ConditionCode'),
                condition.findtext('ConditionData')))
        return content

    @staticmethod
    def get_price(quote):
        prices = quote.findall('QtdSInAdCur')
        # We pick BILLC as the canonical price, since it'e the one that would
        # actually be billed.
        correct_price = None
        for price in prices:
            if price.findtext('CurrencyRoleTypeCode') == 'BILLC':
                correct_price = price
            if correct_price is not None:
                break
        if correct_price is None:
            raise CarrierError(
                "DHL gave a nonsense response to a pricing request.")
        currency = correct_price.find('CurrencyCode').text
        amount = correct_price.find('TotalAmount').text
        return Money(amount, currency)

    @staticmethod
    def timestr(time_string):
        return datetime.strptime(time_string, '%Y-%m-%dPT%HH%MM')

    @staticmethod
    def response_to_dict(quotes):
        return {
            quote.find('GlobalProductCode').text: {
                'service_name': quote.find('LocalProductName').text.title(),
                'delivery_datetime': DHLApi.timestr(
                    quote.find('DeliveryDate').text
                    + quote.find('DeliveryTime').text),
                'price': DHLApi.get_price(quote)}
            for quote in quotes}

    def get_services(self, request):
        pieces = enumerate_pieces(request)
        duties = money_snippet('dutiable.xml', request)
        dutiable = (
            request.origin.country != request.destination.country) and duties
        rate_request = rates_request(
            request, self.request_header, pieces, dutiable, duties)
        response = self.make_call(rate_request)
        response_dict = self.response_to_dict(response.findall('QtdShp'))
        self.cache_results(request, response_dict)
        return {
            Service(self, key, value['service_name']): {
                'price': value['price'],
                'delivery_datetime': value['delivery_datetime']}
            for key, value in response_dict.items()}

    def delivery_datetime(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[tuple(request)].get(service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return data['delivery_datetime']

    def quote(self, service, request):
        if not self.cache_key(request) in self.cache:
            self.get_services(request)
        data = self.cache[self.cache_key(request)].get(
            service.service_id, None)
        if not data:
            raise ExceedsLimitsError(
                "This package is not able to be shipped on this service.")
        return Money(data['price'].amount, data['price'].currency)