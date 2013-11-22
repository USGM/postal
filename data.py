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
    def __init__(
            self, contact_name=None, phone_number=None,
            street_lines=None, city=None, subdivision=None,
            postal_code=None, country=None):
        # The following should always be needed for any country.
        if not all([contact_name, phone_number, street_lines, city, country]):
            raise AddressError(
                "Not enough information to construct an address.")
        self.contact_name = contact_name
        self.phone_number = phone_number
        self.street_lines = street_lines
        self.city = city
        self.postal_code = postal_code
        self.subdivision = subdivision
        try:
            self.country = countries.get(alpha2=country)
        except KeyError:
            raise AddressError("Could not find the requested country.")


class Package:
    """
    A parcel is something that we have not yet committed to ship, but which
    has information like its height, width, and length, as well as its weight.

    These can be used to query other services and find out what options for
    delivery are available.

    The units are stored in centimeters and kilograms, but are assumed to be
    entered in inches and pounds unless imperial=False
    """
    def __init__(
            self, length, width, height, weight,
            address_origin, address_destination, declarations=None,
            insurance=None, imperial=True):
        self.length = length
        self.width = width
        self.height = height
        self.weight = weight
        self.origin = address_origin
        self.destination = address_destination
        self.declarations = declarations
        self.insurance = insurance

        if imperial:
            self.metricize()

    def __hash__(self):
        dimensions = 'x'.join(map(str, sorted(
            [self.length, self.width, self.height, self.weight])))
        return hash((
            dimensions, self.origin.postal_code, self.origin.country,
            self.origin.postal_code, self.destination.country,
            self.destination.postal_code))

    @staticmethod
    def to_centimeters(number):
        return number * 2.54

    @staticmethod
    def to_inches(number):
        return number / 2.54

    @staticmethod
    def to_kilgram(number):
        return number * 0.453592

    @staticmethod
    def to_pounds(number):
        return number / 0.453592

    def metricize(self):
        self.length = self.to_centimeters(self.length)
        self.width = self.to_centimeters(self.width)
        self.height = self.to_centimeters(self.height)


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