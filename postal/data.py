"""
These are the data structures used by Postal in order to represent things like
shipments.
"""
from decimal import Decimal
from datetime import datetime
from money import Money
from pycountry import countries, subdivisions


try:
    import money
except ImportError:
    import Money

from .exceptions import AddressError, NotSupportedError


TWOPLACES = Decimal('0.01')  # used by DHL


# Force pycountry to fetch data.
subdivisions.get(country_code='US')

subdivision_map = {
    country.alpha2:
        {subdivision.code[3:]: subdivision.name for subdivision in subdivisions.get(country_code=country.alpha2)}
        if country.alpha2 in subdivisions.indices['country_code']
        else {}
    for country in countries
}

country_map = {country.name.lower(): country for country in countries}

for code in ('AE', 'AA', 'AP'):
    subdivision_map['US'][code] = code


def get_country(country_code):
    try:
        return countries.get(alpha2=country_code)
    except KeyError:
        raise AddressError('"%s" is not a valid country code.' % country_code)


def stack_values(iterable, func_name):
    result = 0
    for item in iterable:
        result += getattr(item, func_name)()
    if result == 0:
        return money.Money(0, 'USD')  # so as not to break interface
    if str(result.currency) == 'XXX':
        raise Exception("Can't compute sum of different kinds of currencies.")
    return result


def sigfig(amount):
    return Decimal(amount).quantize(TWOPLACES)


class Address(object):
    """
    Addresses for shipping. Many services have address validation, which can
    be used to determine if an address is sane or not.
    """

    def __hash__(self):
        return hash((
            self.country.alpha2, self.city, self.subdivision, self.postal_code,
            self.residential))

    def __init__(
            self, contact_name=None, phone_number=None,
            street_lines=None, city=None, subdivision=None,
            postal_code=None, country=None, residential=False, email=None):
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
        """
        # The following should always be needed for any country.
        if not all([street_lines, city, country]):
            raise AddressError(
                "Not enough information to construct an address.")
        if isinstance(street_lines, str):
            raise TypeError('street_lines should be a sequence of strings, '
                            'not a string')

        self.contact_name = contact_name
        self.phone_number = phone_number
        self.email = email

        self.street_lines = list(street_lines)  # Calling list() to raise
        # exception immediately if parameter is not iterable.

        self.city = city
        self.postal_code = postal_code
        self.subdivision = subdivision
        self.residential = residential
        self.country = get_country(country)

    def _str(self):
        return '    %s %s\n    %s\n    %s, %s %s %s%s' % (
            self.contact_name, self.phone_number, self.street_lines,
            self.city, self.subdivision, self.postal_code,
            getattr(self.country, 'alpha2', 'Unspecified country'),
            ((('\n    Residential' if self.residential else '')))
        )

    def _str_short(self):
        return '%s %s, %s, %s, %s %s %s%s' % (
            self.contact_name, self.phone_number, self.street_lines,
            self.city, self.subdivision, self.postal_code,
            getattr(self.country, 'alpha2', 'Unspecified country'),
            (((' (Residential)' if self.residential else '')))
        )

    def __str__(self):
        return self._str().encode('utf8')

    def __unicode__(self):
        return unicode(self._str())

    def __repr__(self):
        return repr(self._str())

    def to_primitive(self):
        return {
            'street_lines': self.street_lines,
            'city': self.city,
            'country': self.country.alpha2,
            'subdivision': self.subdivision,
            'residential': self.residential,
            'phone_number': self.phone_number,
            'email': self.email,
            'contact_name': self.contact_name,
            'postal_code': self.postal_code,
        }

    def copy(self):
        return Address(
            contact_name=self.contact_name,
            phone_number=self.phone_number,
            street_lines=self.street_lines,  # copied by constructor
            city=self.city,
            subdivision=self.subdivision,
            postal_code=self.postal_code,
            country=self.country.alpha2,
            residential=self.residential
        )

    def cache_hash(self):
        address = 'x'.join(map(str, sorted([
            self.contact_name, self.phone_number, self.street_lines, self.city,
            self.subdivision, self.postal_code, self.country.alpha2, self.residential
        ])))
        return hash(address)


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

    extra_params is where extra, per-carrier information can be stored. Some
    carriers may have extra options which can be used but which are outside
    the scope of the main API. The keys of this database should be the carriers
    and the values dictionaries.

    NOTE: While it is referred to as an insured value, not all carriers provide
    what is legally defined as insurance. The closest analogues are used with
    each carrier in order to allow for filing claims with the carriers if
    something should go wrong.
    """
    def __init__(
            self, origin, destination, packages,
            ship_datetime=None, extra_params=None):
        if extra_params is None:
            self.extra_params = {}
        else:
            self.extra_params = extra_params
        self.origin = origin
        self.destination = destination

        self.packages = list(packages)  # Resolve generators, ensure iterable

        self.ship_datetime = ship_datetime
        if ship_datetime is not None and (ship_datetime < datetime.now()):
            # Ship datetime is in the past. Set to None. Carriers should
            # interpret this as 'now' or the next available shipping
            # opportunity.
            self.ship_datetime = None

    def get_total_declared_value(self):
        return stack_values(self.packages, 'get_total_declared_value')

    def get_total_insured_value(self):
        return stack_values(self.packages, 'get_total_insured_value')

    def shallow_copy(self):
        return Request(
            self.origin, self.destination, self.packages, self.ship_datetime,
            self.extra_params)

    def international(self, origin=None):
        origin = origin or self.origin
        return origin.country.alpha2 != self.destination.country.alpha2

    def total_weight(self):
        return sum([package.weight for package in self.packages])

    def documents_only(self):
        return all([package.documents_only for package in self.packages])

    def all_declarations(self):
        for pack in self.packages:
            for dec in pack.declarations:
                yield dec

    def long_description(self, require_declarations=False):
        """
        Creates a long-form description of this request.
        """
        descriptions = []
        for pack in self.packages:
            if pack.declarations:
                for dec in pack.declarations:
                    descriptions.append(dec.description)
            elif pack.documents_only:
                descriptions.append('documents')
            elif require_declarations:
                raise NotSupportedError('Each package '
                                        "in an international shipment "
                                        "that isn't documents only must "
                                        'have declarations.')
        return ', '.join(descriptions) or 'Documents'

    def _str(self):
        extra_params = dict(self.extra_params)
        if 'invoice' in extra_params:
            extra_params['invoice'] = '[Invoice]'  # Fix for hanging tests

        origin = self.origin and self.origin._str_short()
        destination = self.destination and self.destination._str_short()
        return 'Request(origin=%s, destination=%s, packages=%s' \
               ', ship_datetime=%s, extra_params=%s)' \
               % (origin, destination, self.packages, self.ship_datetime,
                  extra_params)

    def __str__(self):
        return self._str().encode('utf8')

    def __unicode__(self):
        return unicode(self._str())

    def __repr__(self):
        return self._str()


class PackageType(object):
    """
    Represents the type of container a particular set of items is held in,
    like a box, pallet, envelope, or bag/softpak.
    """

    def __init__(self, carrier, code, name):
        self.carrier = carrier
        self.code = code
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, PackageType):
            return NotImplemented
        return (self.carrier == other.carrier) and (self.code == other.code)

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash(self.code)

    def __str__(self):
        return "%s %s" % (getattr(self.carrier, 'name', 'Generic'), self.name)

    def __repr__(self):
        return '<%s|%s:%s>' % (
            getattr(self.carrier, 'name', '???'), self.code, str(self))


class Package(object):
    """
    Package objects represent the parcels that will be shipped and what their
    value is.

    All carriers support imperial units but have spotty support for metric.
    It is with great annoyance that we have therefore made the default units
    imperial. You can convert your measurements on the fly by setting imperial
    to false.

    declarations is a list of Declaration objects, used for customs data
    and for calculating the insured value.

    The document flag can be used to indicate if the contents are documents
    only. You might need this if you're sending a bunch of printed documents in
    a box.
    """
    def __init__(
            self, length, width, height, weight, package_type=None,
            documents_only=False, carrier_conversion=False, declarations=None,
            imperial=True):
        self.length = length
        self.width = width
        self.height = height
        self.weight = weight
        self.carrier_conversion = carrier_conversion
        self.documents_only = documents_only
        if declarations is None:
            self.declarations = []
        else:
            self.declarations = list(declarations)

        if package_type is None:
            package_type = PackageType(None, 'package', 'Package')
        self.package_type = package_type

        if not imperial:
            self.imperialize()

    def copy(self):
        return Package(
            self.length, self.width, self.height, self.weight,
            self.package_type, self.documents_only, self.carrier_conversion,
            self.declarations, True)

    def get_total_declared_value(self):
        return stack_values(self.declarations, 'get_total_value')

    def get_total_insured_value(self):
        return stack_values(self.declarations, 'get_insured_value')

    def cache_hash(self):
        dimensions = 'x'.join(map(str, sorted(
            [self.length, self.width, self.height, self.weight])))
        return hash(dimensions)

    @staticmethod
    def to_centimeters(number):
        return number * Decimal('2.54')

    @staticmethod
    def to_inches(number):
        return number / 2.54

    @staticmethod
    def to_kilograms(number):
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
        return 'Package(%sx%sx%s weight=%s type=%s carrier_conversion=%s ' \
               'declarations=%s)' \
               % (self.length, self.width, self.height, self.weight,
                  repr(self.package_type), self.carrier_conversion,
                  self.declarations)

    def __repr__(self):
        return str(self)

    def __deepcopy__(self, _):
        return Package(
            length=self.length,
            width=self.width,
            height=self.height,
            weight=self.weight,
            carrier_conversion=self.carrier_conversion,
            documents_only=self.documents_only,
            declarations=self.declarations  # copied in constructor
        )

    def __eq__(self, other):
        try:
            return all([
                sorted([self.length, self.width, self.height]) ==
                    sorted([other.length, other.width, other.height]),
                self.weight == other.weight,
                self.carrier_conversion == other.carrier_conversion,
                self.documents_only == other.documents_only,
                self.declarations == other.declarations
            ])
        except AttributeError:
            return False


class Declaration(object):
    """
    Declarations are more useful for international shipments. They allow you to
    specify what is in the package and what the value of these objects are.

    This is also useful when you want to use Insurance, as it automatically
    calculates the total value and is able to request the desired insured
    value from upstream.
    """
    def __init__(
            self, description, value, origin_country, units, insure=False):
        """
        description:string = Human readable name of type of item
        value:money.Money = worth of each unit
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
        if value != 0 and not isinstance(value, Money):
            # zero doesn't really have a unit
            raise TypeError()
        self.value = value
        self.units = units
        self.origin_country = get_country(origin_country)
        self.insure = insure

    def get_total_value(self):
        return self.units * self.value

    def get_insured_value(self):
        if self.insure:
            return self.get_total_value()
        else:
            return 0

    # TODO: Figure out what this is used for and fix whatever that is.
    def get_uninsured_value(self):
        if self.insure:
            return 0
        else:
            return self.get_total_value()

    def _str(self):
        return '%s x%s, %s each' % (self.description, self.units, self.value)

    def __str__(self):
        return self._str().encode('utf8')

    def __repr__(self):
        return ('<Declaration: ' + self._str() + ', insure=%s>' % self.insure)\
            .encode('utf8')

    def __eq__(self, other):
        try:
            return all([
                self.description == other.description,
                self.value == other.value,
                self.units == other.units,
                self.origin_country == other.origin_country,
                self.insure == other.insure])
        except AttributeError:
            return False


class Shipment(object):
    """
    Created when a package has been committed for shipment. Can also be used
    to get options for dealing with a package after a shipment has been
    requested, like cancellation.
    """
    def __init__(self, carrier, tracking_number, transaction_id=None):
        """
        carrier:Carrier
        tracking_number:string = the master tracking number of the shipment
        transaction_id:string = Transaction ID. Used when a tracking number is
        not provided, but a shipment can still be referenced via API.
        """
        self.tracking_number = tracking_number
        self.carrier = carrier
        self.transaction_id = transaction_id

    def cancel(self):
        raise NotImplementedError

    def __str__(self):
        return 'Shipment<carrier:' + repr(self.carrier.name) \
               + ' tracking_number:' + repr(self.tracking_number) + '>'

    def __repr__(self):
        return str(self)
