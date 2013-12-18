"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""
from suds import WebFault
from ..exceptions import CarrierError, PostalError
import re
from suds.plugin import MessagePlugin


class ClearEmpty(MessagePlugin):
    def clear_empty_tags(self, tags):
        for tag in tags:
            children = tag.getChildren()[:]
            if children:
                self.clear_empty_tags(children)
            if re.match(r'^<[^>]+?/>$', tag.plain()):
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
    # multiple packages under a master tracking number.
    multiship = True
    cache = {}

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
            else:
                raise CarrierError(err.message)

    @staticmethod
    def cache_key(request):
        return hash(tuple(sorted(request.packages, key=hash)))

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
        return []

    def get_services(self, request):
        """
        Get all services that this carrier can provide for transporting this
        package. It should return a dictionary with services as the key, and
        values which are dictionaries containing keys for price, and
        delivery_datetime.
        """
        return {}

    def get_service(self, service_id):
        return Service(
            self, service_id, _service_code_to_description[service_id])

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
        Ship a package on the requested service. This should return a Shipment
        object.
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

    def get_param(self, request, param, *args):
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
        if self not in request.extra_params:
            if raise_exception:
                raise KeyError(
                    "%s not found in extra_params for this request object." %
                    self)
            else:
                return default
        if raise_exception:
            return request.extra_params[self][param]
        return request.extra_params[self].get(param, default)


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

    def ship(self, package):
        return self.carrier.ship(self, package)

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