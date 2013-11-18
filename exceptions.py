"""
Some exceptions for handling precarious cases in Postal.
"""


class PostalError(Exception):
    """
    This is the base class for all exceptions specific to Postal.
    """


class AddressError(PostalError):
    """
    Used when an address is invalid in some way.
    """


class CarrierObjection(PostalError):
    """
    Used when a carrier sends back a complaint about a request that was given
    to it.
    """


class ExceedsLimits(PostalError):
    """
    Used when a requested shipment exceeds the limits of a service.
    """