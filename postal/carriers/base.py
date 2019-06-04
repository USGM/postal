"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""
from base64 import b64encode
import sys
import logging
from threading import RLock
from io import BytesIO
from datetime import datetime, timedelta
import inspect
import os
from pprint import pformat
import re
from itertools import izip_longest

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Image
from reportlab.platypus.para import Paragraph

from suds.plugin import MessagePlugin

from ..exceptions import CarrierError, PostalError
from postal.data import PackageType
from postal.exceptions import NotSupportedError


PY3 = sys.version_info[0] == 3


class PostalLogger(object):
    def __init__(self, logger_name=None, carrier_name=None):
        if not logger_name:
            if not carrier_name:
                logger_name = 'postal'
            else:
                logger_name = 'postal.' + carrier_name

        if not carrier_name:
            carrier_name = 'Unknown Carrier'

        self.logger = logging.getLogger(logger_name)
        self.carrier_name = carrier_name
        self.lock = RLock()

    def sent(self, message):
        self.logger.debug(('='*5) + ' SENT ' + ('='*5))
        self.logger.debug(message)

    def received(self, message):
        self.logger.debug(('='*5) + ' RECEIVED ' + ('='*5))
        self.logger.debug(message)

    def shipment_response(self, shipment_dict):
        self.logger.info(pformat(shipment_dict))

    def debug(self, message):
        if (not message) or message == None:
            import traceback
            message = traceback.format_stack()

        # temporarily displaying low-detail debug messages as info level until
        # finding a way to use custom log levels with Django
        self.logger.info(message)

    def debug_header(self, title):
        self.debug((" %s: %s " % (self.carrier_name, title)).center(50, "="))

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)


class ClearEmpty(MessagePlugin):
    def clear_empty_tags(self, tags):
        for tag in tags:
            children = tag.getChildren()[:]
            if children:
                self.clear_empty_tags(children)
            if re.match(r'^<[^>]+?/>$', tag.plain()) and not tag.attributes:
                tag.parent.remove(tag)

    def marshalled(self, context):
        self.clear_empty_tags(context.envelope.getChildren()[:])


class LoggingWebServicePlugin(MessagePlugin):
    """
    Adds logged messages to recent transmissions.
    """
    def __init__(self):
        self.last_sent_message = None
        self.last_received_reply = None

    def sending(self, context):
        if context.envelope:
            self.last_sent_message = context.envelope

    def parsed(self, context):
        if context.reply:
            self.last_received_reply = context.reply.str()

    def last_sent(self):
        return self.last_sent_message

    def last_received(self):
        return self.last_received_reply


class Carrier(object):
    name = 'Undefined Carrier'
    # If a carrier provides Address Validation Services, this should be set
    # to true.
    address_validation = False
    # If a carrier should not be used to make international shipments, this
    # needs to be False.
    international = True
    # If a carrier should not be used to make domestic shipments, this needs
    # to be False.
    domestic = True
    # Set this to true if the carrier automatically corrects the residential
    # status of addresses. This is mostly here to skip a test that makes sure
    # residential fees are being picked up and abstracted away, since a fair
    # comparison would not be possible.
    auto_residential = False
    # Most carriers allow a multiship option, where one request can have
    # multiple packages under a master tracking number. If a carrier doesn't
    # offer that, it should be noted that shipping isn't transaction safe.
    # You will have to handle these carriers differently to clean up after
    # them.
    atomic_multiship = True
    cache = {}

    # Master dictionary of primarily supported Service Codes. Preferably, this
    # should contain all service codes, but it may only contain ones that are
    # known to be safe and sane to use.
    #
    # This is not a public API item, but rather is intended to be used by
    # things like get_all_services() to construct service objects.
    _code_to_description = {}

    GENERIC_PACKAGE = PackageType(None, 'package', 'Package')
    GENERIC_SOFTPAK = PackageType(None, 'softpak', 'Softpak')
    GENERIC_ENVELOPE = PackageType(None, 'envelope', 'Envelope')

    generic_packaging_table = {
        'package': GENERIC_PACKAGE,
        'softpak': GENERIC_SOFTPAK,
        'envelope': GENERIC_ENVELOPE}

    # Table for all proprietary packaging types. Do not list codes for generic
    # or "customer-supplied" packaging types here; they are always called by
    # their generic names.
    _package_id_to_description = {}

    # Translate generic package id types into their IDs for this carrier.
    _generic_package_translation = {}

    # Used to 'convert' generic packaging types to their proprietary types for
    # this carrier. For instance, a normal envelope shipping on FedEx should be
    # stuffed inside a branded FedEx envelope.
    _to_proprietary_packaging = {}

    # Used to determine the min and maximum estimated transit times for a
    # service. While these can't always be guarenteed, they are useful for
    # displaying to users to help them find out when their items will arrive.
    # The keys should be the service codes, and the values should be a tuple of
    # the minimum and maximum number of days a delivery is expected to take.
    # If it's something like 'next day' which is always the same min or max,
    # use the same integer. If it is not possible to estimate, leave the
    # service out of the dictionary altogether.
    _min_max_estimates = {}

    def __init__(self, postal_configuration):
        self.postal_configuration = postal_configuration
        self.logger = PostalLogger(carrier_name=self.name)
        # Add this to any suds clients as a plugin and then use
        # last_sent() and last_received() on it to grab recent messages.
        self.log_service = LoggingWebServicePlugin()
        if not postal_configuration:
            raise PostalError("Postal Configuration not set.")

    def __eq__(self, other):
        if not isinstance(other, Carrier):
            return NotImplemented
        return other.name == self.name

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.name)

    def service_call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as err:
            if hasattr(err, 'document'):
                raise CarrierError(u"{}".format(err.document))
            else:
                raise CarrierError(repr(err))
        finally:
            self.log_transmission(func.client)

    @classmethod
    def service_url(cls, wsdl_name):
        base_path = os.path.split(os.path.abspath(
            inspect.getfile(inspect.currentframe())))[0]
        base_path = os.path.join(base_path, 'wsdl', cls.name.lower())
        full_path = os.path.join(base_path, wsdl_name)
        return "file://%s" % full_path

    @staticmethod
    def cache_key(request, provider=''):
        _cache_key = str(provider)
        _cache_key += str(request.destination.cache_hash())
        for package in request.packages:
            _cache_key += str(package.cache_hash())
        for key in request.extra_params:
            _cache_key += '{key}:{value}'.format(
                key=key,
                value=request.extra_params[key]
            )
        return hash(_cache_key)

    def cache_results(self, request, response_dict, provider=''):
        """
        Avoid looking up information on an object more than we must.
        """
        # For now, we make this in-process.
        self.cache.update({
            self.cache_key(request, provider): {
                'response': response_dict,
                'timestamp': datetime.now()
            }
        })

    def get_from_cache(self, request, provider=''):
        time_to_fetch = datetime.now() - timedelta(minutes=30)
        _cache_key = self.cache_key(request, provider)
        if _cache_key in self.cache:
            if self.cache[_cache_key]['timestamp'] > time_to_fetch:
                return self.cache[_cache_key]['response']
            else:
                del self.cache[_cache_key]
        return False

    def get_all_services(self):
        """
        Get all services that this carrier provides. This list should be as
        comprehensive as practical. If you want services available for a
        specific request, get_services should be used instead.
        """
        return (self.get_service(code)
                for code in self._code_to_description.keys())

    def get_services(self, request):
        """
        Get all services that this carrier can provide for transporting this
        package. It should return a dictionary with services as the key, and
        values which are dictionaries containing keys for price, and
        delivery_datetime.
        """
        raise NotImplementedError

    def get_service(self, service_id):
        if service_id not in self._code_to_description:
            raise NotSupportedError(
                self.name + ' does not support that service.')

        min_transit, max_transit = self._min_max_estimates.get(
            service_id, (None, None))
        return Service(
            self, service_id, self._code_to_description[service_id],
            min_transit, max_transit)

    def get_origin(self, request):
        return request.origin or self.postal_configuration['shipper_address']

    def validate_address(self, address):
        """
        If the carrier implements address validation services, you can set
        those up here.

        This should return a true or false value, as well as a new address
        object, comprised of any fixes upstream sends.
        """
        raise NotImplementedError

    def ship(self, service, request):
        """
        Ships a package on the requested service.

        returns
        {
            'shipment'->Shipment,
            'price'->Money,
            'packages'->{
                Package->{
                    'tracking_number': string,
                    'label': string
                },
                ...
            }
        }
        """
        raise NotImplementedError

    def delivery_datetime(self, service, request):
        """
        Should return either a datetime object with an approximate delivery
        time for a request, or None. If the package cannot be sent through this
        service, an exception should be raised.
        """
        raise NotImplementedError

    def quote(self, service, request):
        """
        Given a service and a request, determine the cost of sending the
        request through that service. If the request cannot be sent through
        that service, an exception should be raised.
        """
        raise NotImplementedError

    @staticmethod
    def get_generic_package_types():
        return Carrier.generic_packaging_table.values()

    def get_package_type(self, code):
        name = self._package_id_to_description.get(code, None)
        if not name:
            # Checking for generic translations in order to properly handle
            # generics that have been translated inappropriately.
            # Translations should never be stored outside of Postal but this
            # function shouldn't fail or raise an exception when they are.
            for generic_code, carrier_code in \
                    self._generic_package_translation.values():
                if code == carrier_code:
                    # This does happen to lose some information about what the
                    # type of the object is because some carriers treat all
                    # generics as "customer-supplied", which is why translated
                    # generics shouldn't be stored outside of Postal.
                    name = Carrier.generic_packaging_table[generic_code].name
                    break

        if not name:
            raise NotSupportedError(
                "No packaging code '%s' for %s." % (code, self.name))
        return PackageType(self, code, name)

    def track(self, identifier):
        """
        Returns tracking information about a shipment, based on tracking number.
        """
        raise NotImplementedError

    def get_all_package_types(self, generics=True):
        """
        Returns all package types supported by this carrier.
        """
        package_types = [
            PackageType(self, code, name)
            for code, name in self._package_id_to_description.items()]
        if generics:
            package_types += self.generic_packaging_table.values()
        return package_types

    def to_proprietary_package_type(self, package_type):
        if package_type.carrier == self:
            return package_type
        if package_type.carrier is None:
            code = self._to_proprietary_packaging.get(package_type.code, None)
            if code:
                return PackageType(
                    self, code, self._package_id_to_description[code])
        raise NotSupportedError("Package type %s is not available on %s."
                                % (package_type, self.name))

    def log_transmission(self, client):
        """
        Log last send/receive action from a SUDs client.
        """
        with self.logger.lock:
            self.logger.debug(self.log_service.last_sent())
            self.logger.debug(self.log_service.last_received())

    def expected_package_type(self, request, package):
        """
        Given a request and a package, returns the package type the package can
        be expected to be converted to if applicable, or the generic if not.
        """
        if not package.carrier_conversion:
            return package.package_type
        if len(request.packages) > 1 and self.atomic_multiship:
            return PackageType(None, 'package', 'Package')

        return self.to_proprietary_package_type(package.package_type)

    def _get_internal_package_type_code(
            self, package_type, to_proprietary=False):
        """
        Converts a package type into the code used when sending a network
        request. Generic package types must always be translated before being
        transmitted but their translations should, for best maintainability,
        never be stored outside of Postal.
        """
        if package_type.carrier == self:
            return package_type.code

        if package_type.carrier is None:
            if to_proprietary:
                if package_type.code in self._to_proprietary_packaging:
                    return self._to_proprietary_packaging[package_type.code]
            # Can't convert so proceed to try a generic instead.
            if package_type.code in self._generic_package_translation:
                return self._generic_package_translation[package_type.code]
            # Not supported at all so fall through to below exception

        raise NotSupportedError("Packaging type %s is not available for %s."
                                % (package_type, self.name))

    def _page(self, canvas, doc):
        canvas.saveState()
        canvas.setFont('Times-Roman', 9)
        canvas.drawCentredString(4.125*inch, .75*inch, '%s' % doc.page)
        canvas.restoreState()

    def commercial_invoice(self, request):
        result = BytesIO()
        signature = request.extra_params.get(
            'ci_signature', self.postal_configuration['ci_signature'])
        logo = request.extra_params.get(
            'ci_shipper_logo',
            self.postal_configuration['ci_shipper_logo'])
        signed_by = request.extra_params.get(
            'ci_signed_by', self.postal_configuration['ci_signed_by'])
        doc = SimpleDocTemplate(result, pagesize=letter)

        style_table_head = ParagraphStyle(
            'table head', fontName='Helvetica-Bold', fontSize=7, wordWrap=True,
            leading=7*1.2, alignment=TA_CENTER)
        style_table_cell = ParagraphStyle(
            'table cell', fontName='Times-Roman', fontSize=10, wordWrap=True,
            leading=10*1.2)
        style_heading = ParagraphStyle(
            'heading', fontName='Helvetica-Bold', fontSize=18, leading=18*1.2)
        style_body = ParagraphStyle(
            'body', fontName='Times-Roman', fontSize=10, wordWrap=True,
            spaceAfter=15)

        elements = []

        elements.append(Paragraph('Commercial Invoice', style_heading))

        logo_reader = ImageReader(BytesIO(logo))
        height = 1.5*inch
        width = height * logo_reader.getSize()[0] / logo_reader.getSize()[1]
        im = Image(BytesIO(logo), width=width, height=height)
        im.hAlign = 'LEFT'
        elements.append(im)

        origin = self.get_origin(request)
        origin_lines = ['Exporter:'] \
                     + [origin.contact_name] \
                     + origin.street_lines \
                     + ['%s, %s %s' % (
                        origin.city, origin.subdivision, origin.postal_code)] \
                     + [origin.country.alpha2] \
                     + [origin.phone_number]

        dest = request.destination
        dest_lines = ['Consignee and Importer:'] \
                   + [dest.contact_name] \
                   + dest.street_lines \
                   + ['%s, %s %s' % (
                      dest.city, dest.subdivision, dest.postal_code)]\
                   + [dest.country.alpha2] \
                   + [dest.phone_number]

        t = Table(
            list(izip_longest(origin_lines, dest_lines, fillvalue='')),
            colWidths=[3.125*inch, 3.125*inch],
            rowHeights=[.15*inch] * max(len(origin_lines), len(dest_lines)))
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Times-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 10)]))
        elements.append(t)

        pairs = [
            ('Total Weight', '%s lbs' % request.total_weight()),
            ('Country of Destination', dest.country.alpha2)]
        for i, (label, info) in enumerate(pairs):
            pairs[i] = (label + ': ', info)

        t = Table(pairs, rowHeights=[.15*inch] * len(pairs))
        t.hAlign = TA_LEFT
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Times-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 0), (-1, -1), 10)]))
        elements.append(t)

        rows = [
            [Paragraph(a, style_table_head)
             for a in ['Line', 'Description', 'Harmonized Code',
                       'Country of Origin', 'Quantity',
                       'Value', 'Line Total']]]
        for i, dec in enumerate(request.all_declarations(), 1):
            rows.append([
                '%s' % i,
                Paragraph(dec.description, style_table_cell),
                '', dec.origin_country.alpha2,
                '%s' % dec.units, '%s' % dec.value,
                '%s' % dec.get_total_value()])
        rows.append([
            '', '', '', '', '',
            'Total:', '%s' % request.get_total_declared_value()])

        t = Table(rows, colWidths=[
            .3 * inch, 2.5 * inch, .6 * inch, .6 * inch,
            .5 * inch, .9 * inch, .9 * inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 7),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGNMENT', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGNMENT', (0, 1), (0, -1), 'CENTER'),
            ('ALIGNMENT', (2, 1), (6, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Times-Roman'),
            ('FONTSIZE', (0, 1), (-1, -1), 10)]))
        elements.append(t)

        elements.append(Paragraph(
            'These commodities, technology, or software were exported from '
            'the United States in accordance with the '
            'Export Administration regulations. Diversion contrary to U.S. '
            'law is prohibited.',
            style=style_body))

        elements.append(Paragraph(
            'I declare all information in this invoice to be '
            'true and correct.',
            style=style_body))

        signature_reader = ImageReader(BytesIO(signature))
        height = .75*inch
        width = (height * signature_reader.getSize()[0] /
                 signature_reader.getSize()[1])
        im = Image(BytesIO(signature), width=width, height=height)
        im.hAlign = 'LEFT'
        elements.append(im)

        # horizontal line
        t = Table([['']], colWidths=[6.5*inch])
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1, colors.black)]))
        elements.append(t)

        elements.append(Paragraph(
            'Signature of authorized person', style=style_body))
        elements.append(Paragraph(
            'Signed by %s on %s' % (
                signed_by, datetime.now().strftime('%b %d, %Y, %I:%M %p')),
            style=style_body))

        doc.build(elements, onFirstPage=self._page, onLaterPages=self._page)
        return b64encode(result.getvalue())


class Service(object):
    def __init__(self, carrier, service_id, name,
                 min_transit=None, max_transit=None):
        self.carrier = carrier
        # Unique identifier for use with a carrier's get_service() method.
        # This should always be a string.
        self.service_id = service_id
        # The display name for a service, such as 'Priority Mail International'
        self.name = name
        # The minimum estimated days of transit.
        self.min_transit = min_transit
        # The max.
        self.max_transit = max_transit

    def __str__(self):
        return "%s: %s" % (self.carrier.name, self.name)

    def __repr__(self):
        return "<%s>" % str(self)

    def __hash__(self):
        return hash((self.carrier.name, self.service_id))

    def __eq__(self, other):
        if not hasattr(other, 'service_id'):
            return NotImplemented
        if not hasattr(other, 'carrier'):
            return NotImplemented
        return (
            self.service_id == other.service_id) and (
                self.carrier == other.carrier)

    def __ne__(self, other):
        return not self.__eq__(other)

    def price(self, request):
        """
        If a carrier can't ship a package on this service, this should raise
        an exception.
        """
        return self.carrier.quote(self, request)

    def ship(self, request):
        return self.carrier.ship(self, request)

    def request_pickup(self, request):
        """
        Should return a date or something. TBD.
        """
        return self.carrier.request_pickup(self.carrier, request)

    def delivery_datetime(self, request):
        """
        Get the expected delivery date of a package.
        """
        return self.carrier.delivery_datetime(self, request)

    def database_name(self):
        return self.carrier.name + '|' + self.service_id
