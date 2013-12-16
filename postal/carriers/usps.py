"""
This is the module for interfacing with the United States Postal Service web
API. Unfortunately, USPS does not provide a WSDL specification, and so we are
bereft of the ability to use a library like Suds to do a lot of the lifting
for us.
"""
from base import Carrier


class USPSApi(Carrier):
    """
    Implements calls to the USPS web API.
    """
    def __init__(self, username, password, postal_configuration=None):
        super(USPSApi, self).__init__(postal_configuration)
        self.username = username
        self.password = password

    def get_services(self, parcel=None):
        """
        Get available services, optionally constraining them to a parcel.
        """

# Need to find a way to dynamically get all carriers.
# Also need to find a proper way to specify their inits.
carriers = [USPSApi]