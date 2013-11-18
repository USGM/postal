"""
These are the data structures used by Postal in order to represent things like
shipments.
"""

from pycountry import countries

from exceptions import AddressError


class Address:
    """
    Addresses for shipping. Many services have address validation, which can
    be used to determine if an address is sane or not.
    """
    def __init__(self, address, subdivision, postal_code, country):
        self.address = address
        self.subdivision = subdivision
        self.postal_code = postal_code
        self.country = country

        if self.country not in countries:
            raise AddressError


class Package:
    """
    A parcel is something that we have not yet committed to ship, but which
    has information like its height, width, and length, as well as its weight.

    These can be used to query other services and find out what options for
    delivery are available.
    """
    def __init__(
            self, length, width, height, weight,
            address_origin, address_destination, declarations=None,
            insurance=None):
        self.length = length
        self.width = width
        self.height = height
        self.weight = weight
        self.origin = address_origin
        self.destination = address_destination
        self.declarations = declarations
        self.insurance = insurance


class Shipment:
    """
    Created when a package has been committed for shipment.
    """

    def __init__(self, parcel, service):
        self.parcel = parcel
        self.service = service

        self.tracking_number, self.label = self.service.ship(parcel)

    def request_pickup(self, date):
        """
        Should return expected pickup time.
        """
        return self.service.request_pickup(self.tracking_number, date)