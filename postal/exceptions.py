"""
Some exceptions for handling precarious cases in Postal.
"""


class PostalError(Exception):
    """
    This is the base class for all exceptions specific to Postal.
    """
    def __init__(self, *args, **kwargs):
        self.code = kwargs.pop('code', None)
        super(PostalError, self).__init__(*args, **kwargs)


class AddressError(PostalError):
    """
    Used when an address is invalid in some way.
    """
    def __init__(self, *args, **kwargs):
        """
        If a carrier complains about a specific field, details should go here.
        """
        self.fields = kwargs.pop('fields', {})
        super(AddressError, self).__init__(*args, **kwargs)


class CarrierError(PostalError):
    """
    Used when a carrier sends back a complaint about a request that was given
    to it.
    """


class NotSupportedError(PostalError):
    """
    Used when a requested shipment exceeds the limits of a service.
    """