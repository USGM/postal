"""
These are the data structures used by Postal in order to represent things like
shipments.
"""

from pycountry import countries
import money

from exceptions import AddressError


def get_country(country_code):
    try:
        return countries.get(alpha2=country_code)
    except KeyError:
        raise AddressError("Could not find the requested country.")


class Address(object):
    """
    Addresses for shipping. Many services have address validation, which can
    be used to determine if an address is sane or not.
    """
    def __init__(
            self, contact_name=None, phone_number=None,
            street_lines=None, city=None, subdivision=None,
            postal_code=None, country=None, residential=False,
            urbanization=None):
        """
        contact_name:string
        phone_number:string
        street_lines:[string] = list of each line of the street address,
            i.e. ['123 Whatever Lane', 'Box #123']
        city:string
        subdivision:string:len=2 = postal abbreviation of state or province
        postal_code:string|None = the postal code or None if not applicable in
            the specified country
        postal_code_extension:(string:len=4)|None = the postal code extension
            or None if not in the US
        country:string:len=2 = 2-letter abbreviation of the country name
            (the alpha2 code)
        residential:bool = true if this object represents a residential address
        urbanization:string|None = sub-city political division; must be None
            if country is not 'PR'/Puerto Rico (required for UPS)
        """
        # The following should always be needed for any country.
        if not all([contact_name, phone_number, street_lines, city, country]):
            raise AddressError(
                "Not enough information to construct an address.")
        if urbanization is not None and country != 'PR':
            raise AddressError('Urbanization given for non-PR address.')

        self.contact_name = contact_name
        self.phone_number = phone_number

        self.street_lines = list(street_lines)  # Calling list() to raise
        # exception immediately if parameter is not iterable.

        self.city = city
        self.postal_code = postal_code
        self.subdivision = subdivision
        self.residential = residential
        self.country = get_country(country)
        self.urbanization = urbanization

    def __str__(self):
        return (
            self.contact_name + ' ' + self.phone_number + '\n' +
            str(self.street_lines) + '\n' +
            self.city + ', ' + self.subdivision + ' ' +
            str(self.postal_code) +
            (
                ' urbanization: ' + self.urbanization
                if self.urbanization is not None else
                ''
            ) + ' ' + self.country.alpha2 + '\n' +
            'Residential: ' + str(self.residential)
        )

    def __repr__(self):
        return '<\n' + str(self) + '\n>'


class Request(object):
    """
    This object represents a full request to send to one of the carriers.
    It can contain several packages.

    packages should contain a list of Package objects.

    origin and destination should be Address objects.

    ship_datetime should be set to the time when the shipment is expected to
    be made.

    When insure is set true, API calls will declare the value of items in a way
    that intends to pay for an insurance surcharge, if one is available.

    NOTE: While it is referred to as an insured value, not all carriers provide
    what is legally defined as insurance. The closest analogues are used with
    each carrier in order to allow for filing claims with the carriers if
    something should go wrong.
    """
    def __init__(self, origin, destination,
                 packages, ship_datetime=None, insure=False):
        self.origin = origin
        self.destination = destination
        self.insure = insure

        self.packages = list(packages)  # Calling list() to raise exception
        # immediately if parameter is not iterable.

        self.ship_datetime = ship_datetime

    def get_total_declared_value(self):
        result = 0
        for pak in self.packages:
            for dec in pak.declarations:
                result += dec.value
        if result == 0:
            return money.Money(0, 'USD')  # so as not to break interface
        return result


class Package(object):
    """
    Package objects represent the parcels that will be shipped and what their
    value is.

    All carriers support Imperial units, but have spotty support for Metric.
    It is with great annoyance that we have therefore made the default units
    imperial. You can convert your measurements on the fly by setting imperial
    to false.

    declarations is a list of Declaration objects, used for customs data
    and for calculating the insured value.


    """
    def __init__(
            self, length, width, height, weight, declarations=None,
            imperial=True):
        self.length = length
        self.width = width
        self.height = height
        self.weight = weight
        if declarations is None:
            self.declarations = []
        else:
            self.declarations = declarations

        if not imperial:
            self.imperialize()

    def __hash__(self):
        dimensions = 'x'.join(map(str, sorted(
            [self.length, self.width, self.height, self.weight])))
        return hash(dimensions)

    @staticmethod
    def to_centimeters(number):
        return number * 2.54

    @staticmethod
    def to_inches(number):
        return number / 2.54

    @staticmethod
    def to_kilogram(number):
        return number * 0.453592

    @staticmethod
    def to_pounds(number):
        return number / 0.453592

    def imperialize(self):
        self.length = self.to_inches(self.length)
        self.width = self.to_inches(self.width)
        self.height = self.to_inches(self.height)
        self.weight = self.to_pounds(self.weight)

    def __str__(self):
        return (
            'Package(length=' + repr(self.length) + ', width=' +
            repr(self.width) + ', height=' + repr(self.height) + ', weight=' +
            repr(self.weight) + ', declarations=' + repr(self.declarations) +
            ')'
        )

    def __repr__(self):
        return str(self)


class Declaration(object):
    """
    Declarations are more useful for international shipments. They allow you to
    specify what is in the package and what the value of these objects are.

    This is also useful when you want to use Insurance, as it automatically
    calculates the total value and is able to request the desired insured
    value from upstream.
    """
    def __init__(self, description, value, origin_country, units):
        """
        description:string = Human readable name of type of item
        value:money.Money = worth of item
        origin_country:string:alpha2 = alpha2 abbreviation of country
        units:integer = ?

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


class Shipment(object):
    """
    Created when a package has been committed for shipment. Can also be used
    to get options for dealing with a package after a shipment has been
    requested, like cancellation.
    """
    def __init__(self, carrier, tracking_number, package_details=None):
        """
        carrier:Carrier
        tracking_number:string = the master tracking number of the shipment
        package_details:{
            Package --> {
                'tracking_number' --> string,
                'label' --> string = raw binary data of image of shipping label
            },
            ...
        }
        """

        self.tracking_number = tracking_number
        if carrier:
            self.carrier = carrier
        else:
            self.derive_carrier()
        self.package_details = package_details

    def derive_carrier(self):
        # Reverse engineer the carrier based on the tracking number, somehow.
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError
