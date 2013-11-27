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


class Carrier(object):

    def __init__(self):
        pass

    @staticmethod
    def service_call(client, func_name, *args, **kwargs):
        try:
            return getattr(client.service, func_name)(*args, **kwargs)
        except WebFault as err:
            raise CarrierError(err.document)

    def get_services(self, package):
        return []

    def validate_address(self, address):
        """
        If the carrier implements address validation services, you can set
        those up here.

        This should return a true or false value, as well as a new address
        object, comprised of any fixes upstream sends.
        """
        raise NotImplementedError

    def delivery_datetime(self, service, package):
        """
        Should return either a datetime object with an approximate delivery
        time for a package, or None. If the package cannot be sent through this
        service, an exception should be raised.
        """
        raise NotImplementedError

    def quote(self, service, package):
        """
        Given a service and a package, determine the cost of sending the
        package through that service. If the package cannot be sent through
        that service, an exception should be raised.
        """
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

    def price(self, package):
        """
        If a carrier can't ship a package on this service, this should raise
        an exception.
        """
        return self.carrier.quote(self, package)

    def request_pickup(self, package):
        """
        Should return a date or something. TBD.
        """
        return self.carrier.request_pickup(self.carrier, package)

    def delivery_datetime(self, package):
        """
        Get the expected delivery date of a package.
        """
        return self.carrier.delivery_datetime(self, package)