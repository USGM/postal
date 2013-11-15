"""
Front-end for the Postal Library.
"""

import inspect
import pkgutil

import carriers
from exceptions import PostalError


class Postal:
    def __init__(self, configuration=None):
        carriers = []
        if configuration:
            self.configuration = configuration
        else:
            raise PostalError("No configuration provided.")

        for module in inspect.getmembers(carriers, inspect.ismodule):
            if hasattr(module, 'carriers'):
                carriers.update(module.carriers)

        self.carriers = carriers

    def get_options(self, package):
        return {
            carrier: carrier.get_services(package)
            for carrier in self.carriers}