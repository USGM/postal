"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""
import inspect
import os
import re

from suds.plugin import MessagePlugin

from ..exceptions import CarrierError, PostalError
from postal.data import PackageType
from postal.exceptions import NotSupportedError


class ClearEmpty(MessagePlugin):
    def clear_empty_tags(self, tags):
        for tag in tags:
            children = tag.getChildren()[:]
            if children:
                self.clear_empty_tags(children)
            if re.match(r'^<[^>]+?/>$', tag.plain()):
                if not tag.attributes:
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

    # Generic packaging types that are usually shippable on all services.
    generic_packaging_table = {
        # Generic box
        'package': 'Package',
        # Bubble wrapped envelope
        'softpak': 'Softpak',
        'envelope': 'Envelope'}

    # Table for all supported packaging types, aside from the generics.
    _package_id_to_description = {}

    # Translate generic package id types into their IDs for this carrier.
    _generic_package_translation = {}

    # Used to 'convert' generic packaging types to their proprietary types for
    # this carrier. For instance, a normal envelope shipping on FedEx should be
    # stuffed inside a branded FedEx envelope.
    _to_proprietary_packaging = {}

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
            request.packages, key=lambda x: x.cache_hash)))

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
        return (
            Service(self, code, name)
            for code, name in self._code_to_description.items())

    def get_services(self, request):
        """
        Get all services that this carrier can provide for transporting this
        package. It should return a dictionary with services as the key, and
        values which are dictionaries containing keys for price, and
        delivery_datetime.
        """
        raise NotImplementedError

    def get_service(self, service_id):
        try:
            return Service(
                self, service_id, self._code_to_description[service_id])
        except KeyError:
            raise NotSupportedError()

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
        return [
            PackageType(
                None, code, name)
            for code, name in Carrier.generic_packaging_table.items()]

    def get_package_type(self, code):
        name = self._package_id_to_description.get(code, None)
        if not name:
            raise NotSupportedError(
                "No packaging code '%s' for %s." % (code, self.name))
        return PackageType(self, code, name)

    def get_all_package_types(self, generics=True):
        """
        Returns all package types supported by this carrier.
        """
        package_types = [
            PackageType(
                self, code, name)
            for code, name in self._package_id_to_description.items()]
        if generics:
            package_types += [
                PackageType(None, code, name)
                for code, name in self.generic_packaging_table.items()]
        return package_types

    def package_type_translate(self, package_type, proprietary=False):
        """
        Takes a package type, verifies it can be used on this carrier, and
        converts it to a version that can be used with this carrier if it's
        generic. If proprietary is true, will attempt to bump up to proprietary
        packaging.
        """
        code = package_type.code
        supported_types = self._generic_package_translation.keys()
        supported_types += self._package_id_to_description.keys()
        supported_types += self._to_proprietary_packaging.keys()
        if code not in supported_types:
            raise NotSupportedError(
                "Packaging type %s is not available on %s." % (
                    package_type, self.name))
        if package_type.carrier != self and package_type.carrier is not None:
            raise NotSupportedError(
                "Packaging type %s is not available on %s." % (
                    package_type, self.name))
        elif package_type.carrier == self:
            return package_type
        prop_code = self._to_proprietary_packaging.get(code, None)
        if proprietary and prop_code:
            return PackageType(
                self, prop_code, self._package_id_to_description[prop_code])
        generic_code = self._generic_package_translation.get(code, None)
        if not generic_code:
            raise NotSupportedError(
                "Package type %s is not available on %s." % (
                    package_type, self.name))
        # If we're here, we're just changing the code to the carrier's
        # proprietary one.
        return PackageType(self, generic_code, package_type.name)


class Service(object):
    def __init__(self, carrier, service_id, name):
        self.carrier = carrier
        # Unique identifier for use with a carrier's get_service() method.
        # This should always be a string.
        self.service_id = service_id
        # The display name for a service, such as 'Priority Mail International'
        self.name = name

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
