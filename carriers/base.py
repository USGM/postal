"""
This contains the base carrier class. All carriers should
inherit from this class. This also serves as a reference to see what functions
and attributes are expected for all carrier objects.

This module also contains the base Service class. Service objects are
instantiated by Carrier classes to describe a method by which a package may
be sent.
"""

from money import Money


class Carrier:
    def get_services(self, package=None):
        return []

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

    def get_price(self, package):
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