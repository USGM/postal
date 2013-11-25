"""
These are the data structures used by Postal in order to represent things like
shipments.
"""

from pycountry import countries

from exceptions import AddressError


def get_country(country_code):
    try:
        return countries.get(alpha2=country_code)
    except KeyError:
        raise AddressError("Could not find the requested country.")


class Address:
    """
    Addresses for shipping. Many services have address validation, which can
    be used to determine if an address is sane or not.
    """
    def __init__(
            self, contact_name=None, phone_number=None,
            street_lines=None, city=None, subdivision=None,
            postal_code=None, country=None, residential=False):
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
        self.residential = residential
        self.country = get_country(country)


class Package:
    """
    A parcel is something that we have not yet committed to ship, but which
    has information like its height, width, and length, as well as its weight.

    These can be used to query other services and find out what options for
    delivery are available.

    The units are stored in centimeters and kilograms, but are assumed to be
    entered in inches and pounds unless imperial=False

    ship_datetime should be set to the time you expect to be able to ship the
    package.

    declarations is a list of Declaration objects, used for customs data
    and for calculating the insured value.

    When insure is set true, API calls will declare the value of items in a way
    that intends to pay for an insurance surcharge, if one is available.

    NOTE: While it is referred to as an insured value, not all carriers provide
    what is legally defined as insurance. The closest analogues are used with
    each carrier in order to allow for filing claims with the carriers if
    something should go wrong.
    """
    def __init__(
            self, length, width, height, weight,
            address_origin, address_destination, declarations=None,
            insure=False, imperial=True, ship_datetime=None):
        self.length = length
        self.width = width
        self.height = height
        self.weight = weight
        self.origin = address_origin
        self.destination = address_destination
        self.declarations = declarations
        self.insure = insure
        self.ship_datetime = ship_datetime

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


class Declaration:
    """
    Declarations are more useful for international shipments. They allow you to
    specify what is in the package and what the value of these objects are.

    This is also useful when you want to use Insurance, as it automatically
    calculates the total value and is able to request the desired insured
    value from upstream.
    """
    def __init__(self, description, value, origin_country, units):
        """
        Special note: If you've got some item that can't be measured in pieces,
        (such as a liquid), try putting the proper units in the name, and
        setting units to 1. For example:

        Water (64 fl oz)

        Of course, if you have several 64 fl oz jugs of water, you should
        set the number of units to how many you have.
        """
        self.description = description
        self.value = value
        self.units = units
        self.origin_country = get_country(origin_country)


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