"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""
from io import BytesIO
from datetime import datetime
import inspect
import os
from pprint import pformat
import re
from reportlab.lib.pagesizes import letter
import sys
import logging
from threading import RLock
from reportlab.lib.utils import ImageReader

from suds.plugin import MessagePlugin
from PIL import Image, ImageFont, ImageDraw

from ..exceptions import CarrierError, PostalError
from postal.data import PackageType
from postal.exceptions import NotSupportedError

from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.units import mm, inch
from reportlab.pdfbase import pdfmetrics


PY3 = sys.version_info[0] == 3


class PostalLogger(object):
    def __init__(self, logger_name, carrier_name):
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
        # temporarily displaying low-detail debug messages as info level until
        # finding a way to use custom log levels with Django
        self.logger.info(message)

    def debug_header(self, title):
        self.debug(
            ('='*10) + ' ' + str(self.carrier_name) + ': ' + str(title) + ' '
            + ('='*10))

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)


def get_logger(logger_name, carrier_name):
    return PostalLogger(logger_name, carrier_name)


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

    @staticmethod
    def service_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as err:
            if hasattr(err, 'document'):
                raise CarrierError(err.document)
            #elif str(err.message).strip():
            #    raise CarrierError(str(err.message))
            else:
                raise CarrierError(repr(err))

    @classmethod
    def service_url(cls, wsdl_name):
        base_path = os.path.split(os.path.abspath(
            inspect.getfile(inspect.currentframe())))[0]
        base_path = os.path.join(base_path, 'wsdl', cls.name.lower())
        full_path = os.path.join(base_path, wsdl_name)
        return "file://%s" % full_path

    @staticmethod
    def cache_key(request):
        return hash(tuple(sorted(
            request.packages, key=lambda x: x.cache_hash())))

    def cache_results(self, request, response_dict):
        """
        Avoid looking up information on an object more than we must.
        """
        # For now, we make this in-process.
        self.cache.update({self.cache_key(request): response_dict})

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

    @classmethod
    def get_param(cls, request, param, *args):
        """
        Get carrier-specific extra configuration information from request
        object.

        *args: [] | [object] = one object to use as the default value or no
                               extra arguments to raise an exception if no
                               parameter of the specified name is found
        """
        default = None
        raise_exception = False
        try:
            default = args[0]
        except IndexError:
            raise_exception = True
        if len(args) > 1:
            # To make it a bit more like a dict's .get()
            raise TypeError("get_param expected at most 3 arguments, got %i." %
                            (len(args) + 2))
        if cls.name not in request.extra_params:
            if raise_exception:
                raise KeyError(
                    "%s not found in extra_params for this request object." %
                    cls.name)
            else:
                return default
        if raise_exception:
            return request.extra_params[cls.name][param]
        return request.extra_params[cls.name].get(param, default)

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
            for generic_code, carrier_code in self._generic_package_translation.values():
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

    def _draw_text_line(self, canvas, font_tuple, text, space_after=0, space_before=0):
        font_name, font_size = font_tuple

        face = pdfmetrics.getFont('Helvetica').face
        ascent = (face.ascent * font_size) / 1000.0
        descent = (face.descent * font_size) / 1000.0
        line_height = ascent - descent

        canvas.translate(0, -line_height - space_before)
        canvas.setFont(font_name, size=font_size)
        canvas.drawString(0, 0, text)
        canvas.translate(0, -space_after)

    def _draw_image_line(self, canvas, image_reader, height=None):
        if not height:
            width, height = image_reader.getSize()
        else:
            width = height * image_reader.getSize()[0] / image_reader.getSize()[1]
        canvas.translate(0, -height)
        canvas.drawImage(image_reader, 0, 0, width, height)

    def commercial_invoice(
            self, request, logo, signature, signed_by, extra_info={}):
        logo = ImageReader(logo)

        result = BytesIO()
        c = Canvas(result, pagesize=letter)
        print c.getAvailableFonts()

        c.translate(1*inch, 10*inch)

        font_heading = ('Helvetica', 20)
        font_label = ('Times-Bold', 11)
        font_body = ('Times-Roman', 10)

        self._draw_text_line(c, font_heading, 'Commercial Invoice')
        self._draw_image_line(c, logo, height=120)
        self._draw_text_line(c, font_label, 'Exporter:', space_before=10, space_after=5)

        origin = self.get_origin(request)
        lines = [origin.contact_name] \
              + origin.street_lines \
              + ['%s, %s %s' % (
                 origin.city, origin.subdivision, origin.postal_code)] \
              + [origin.country.alpha2] \
              + [origin.phone_number]
        for line in lines:
            self._draw_text_line(c, font_body, line, space_before=2)

        dest = request.destination
        lines = [dest.contact_name] \
              + dest.street_lines \
              + [dest.city + ', ' + dest.subdivision + ' ' + dest.postal_code]\
              + [dest.country.alpha2] \
              + [dest.phone_number]
        # for i, line in enumerate(lines):
        #     draw.text((900, 750 + i * 40), line, font=font_body, fill=0)

        c.translate(0, -10)
        pairs = [
            ('Total Weight', '%s lbs' % request.total_weight()),
            ('Country of Destination', dest.country.alpha2)
        ] + extra_info.items()
        for label, info in pairs:
            self._draw_text_line(c, font_label, label + ': ', space_before=2)
            # draw.text(
            #     (left_margin, line_y), label + ': ', font=font_label, fill=0)
            #
            # w, h = font_label.getsize(label + ': ')
            # draw.text((left_margin + w, line_y), info, font=font_body, fill=0)


        # tx = c.beginText(1*inch, 1*inch)
        # tx.setFont('Helvetica', size=20)
        # tx.textLines('Commercial Invoice\n68rui76ri6u8n ig7fo7f8o7o87o 87fo87fo87fo78 87fo78fgi7gfo87fo7 87fogfki7ufkl7')
        # c.drawText(tx)

        c.showPage()



        tx = c.beginText(1*inch, 2*inch)
        tx.setFont('Helvetica', size=20)
        tx.textLines('Commercial Invoice\n68rui76ri6u8n ig7fo7f8o7o87o 87fo87fo87fo78 87fo78fgi7gfo87fo7 87fogfki7ufkl7')
        c.drawText(tx)

        c.save()
        return result.getvalue()






        im = Image.new("RGB", (200 * 8 + 100, 200 * 11), "white")

        font_head = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf", 40)
        font_table_head = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf", 20)
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf", 30)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf", 30)
        font_table_cell = ImageFont.truetype("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf", 25)

        draw = ImageDraw.Draw(im)

        left_margin = 200
        right_margin = 200 * 8 + 100 - 200
        margin_width = right_margin - left_margin

        draw.text(
            (left_margin, 200), "Commercial Invoice", font=font_head, fill=0)

        line_y = 275

        logo_height = 300
        if logo:
            logo = logo.resize((int(logo_height * logo.size[0] / logo.size[1]), logo_height), Image.ANTIALIAS)
            im.paste(logo, (left_margin, line_y, left_margin + logo.size[0], line_y + logo.size[1]))
        else:
            draw.rectangle((left_margin, line_y, left_margin + 375, line_y + logo_height), fill='#888')

        draw.text((left_margin, 700), "Exporter:", font=font_label, fill=0)

        origin = self.get_origin(request)
        lines = [origin.contact_name] \
              + origin.street_lines \
              + ['%s, %s %s' % (
                 origin.city, origin.subdivision, origin.postal_code)] \
              + [origin.country.alpha2] \
              + [origin.phone_number]

        for i, line in enumerate(lines):
            draw.text((left_margin, 750 + i * 40), line, font=font_body, fill=0)

        draw.text(
            (900, 700), "Consignee and Importer:", font=font_label, fill=0)

        dest = request.destination
        lines = [dest.contact_name] \
              + dest.street_lines \
              + [dest.city + ', ' + dest.subdivision + ' ' + dest.postal_code]\
              + [dest.country.alpha2] \
              + [dest.phone_number]

        for i, line in enumerate(lines):
            draw.text((900, 750 + i * 40), line, font=font_body, fill=0)

        line_y = 1050

        pairs = [
            ('Total Weight', '%s lbs' % request.total_weight()),
            ('Country of Destination', dest.country.alpha2)
        ] + extra_info.items()
        for label, info in pairs:
            draw.text(
                (left_margin, line_y), label + ': ', font=font_label, fill=0)

            w, h = font_label.getsize(label + ': ')
            draw.text((left_margin + w, line_y), info, font=font_body, fill=0)

            line_y += 40

        rows = [
            ('Line', 'Description', 'Harmonized Code', 'Country of Origin',
             'Quantity', 'Value', 'Line Total')
        ]
        for i, dec in enumerate(request.all_declarations(), 1):
            rows.append((
                '%s' % i, dec.description, '', dec.origin_country.alpha2,
                '%s' % dec.units, '%s' % dec.value, '%s' % dec.get_total_value()))
        rows.append((
            '', '', '', '', '',
            'Total:', '%s' % request.get_total_declared_value()))

        line_y += 20

        for i, row in enumerate(rows):
            if i == 0:
                font = font_table_head
            else:
                font = font_table_cell

            for j, cell in enumerate(row):
                draw.text((left_margin + j * 190, line_y), cell,
                          font=font, fill=0)
            line_y += 40
        line_y += 20

        draw.text(
            (left_margin, line_y),
            'These commodities, technology, or software were exported from '
            'the United States in accordance with the',
            font=font_body, fill=0)

        line_y += 40

        draw.text(
            (left_margin, line_y),
            'Export Administration Regulations. Diversion contrary to U.S. '
            'law is prohibited.',
            font=font_body, fill=0)

        line_y += 60

        draw.text(
            (left_margin, line_y),
            'I declare all information in this invoice to be true and correct.',
            font=font_body, fill=0)

        line_y += 50

        signature_height = 100

        if signature:
            signature = signature.resize(
                (int(signature_height * signature.size[0] / signature.size[1]), signature_height),
                Image.ANTIALIAS)
            im.paste(signature, (left_margin, line_y, left_margin + signature.size[0], line_y + signature.size[1]))
        else:
            signature_bounds = (
                left_margin, line_y, left_margin + 800, line_y + signature_height)
            draw.rectangle(signature_bounds, fill='#888')

        line_y += signature_height + 20

        draw.line((left_margin, line_y, 1000, line_y), fill=0, width=2)

        line_y += 20

        draw.text(
            (left_margin, line_y), 'Signature of authorized person',
            font=font_body, fill=0)

        line_y += 30

        draw.text(
            (left_margin, line_y),
            'Signed by %s on %s' % (
                signed_by, datetime.now().strftime('%b %d, %Y, %I:%M %p')),
            font=font_body, fill=0)

        return [im]


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
