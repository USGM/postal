"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""
from suds import WebFault
from ..exceptions import CarrierError
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

    def __init__(self):
        pass

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
        except WebFault as err:
            raise CarrierError(err.document)

    def get_services(self, request):
        """
        Get all services that this carrier can provide for transporting this
        package. It should return a dictionary with services as the key, and
        values which are dictionaries containing keys for price, and
        delivery_datetime.
        """
        return {}

    def validate_address(self, address):
        """
        If the carrier implements address validation services, you can set
        those up here.

        This should return a true or false value, as well as a new address
        object, comprised of any fixes upstream sends.
        """
        raise NotImplementedError

    def delivery_datetime(self, service, request):
        """
        Should return either a datetime object with an approximate delivery
        time for a package, or None. If the package cannot be sent through this
        service, an exception should be raised.
        """
        raise NotImplementedError

    def quote(self, service, request):
        """
        Given a service and a package, determine the cost of sending the
        package through that service. If the package cannot be sent through
        that service, an exception should be raised.
        """
        raise NotImplementedError

    def ship(self, service, request):
        raise NotImplementedError


class Service:
    def __init__(
            self, carrier, service_id, name):
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