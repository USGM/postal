"""
Front-end for the Postal Library.
"""

import threading
from Queue import Queue
import sys
import itertools
from .exceptions import PostalError, NotSupportedError


class Postal:
    def __init__(self, configuration_dict):
        """
        configuration_dict:{
            'enabled_carriers' -> [Carrier, ...],
            'default_currency' -> string:len=3 = currency code, like 'USD',
            'company_name' -> string,
            'carrier_inits' -> {
                string = name of carrier class without trailing 'Api' ->
                    kwargs:dict = arguments for each carrier's constructor,
                ...
            },
            'shipper_address' -> data.Address
        }
        """
        self.carriers = {carrier.name: carrier
                         for carrier in configuration_dict['enabled_carriers']}
        carrier_configs = configuration_dict['carrier_inits']
        for name, carrier in self.carriers.items():
            try:
                self.carriers[name] = carrier(
                    postal_configuration=configuration_dict,
                    **carrier_configs[name])
            except:
                print 'Error while constructing carrier ' + str(name)
                raise

        # Give carriers a back reference to the main postal object.
        configuration_dict['postal'] = self

    def options(self, request):
        """
        Gets all service options from all carriers.

        returns:

        {
            carrier:carriers.Carrier -> {
                'services' -> dict|None= result of carrier.get_services()
                                         or None if unsuccessful,
                'error' -> Exception|None= the problem that occurred
                                           or None if successful
            },
            ... = all loaded carriers represented exactly once
        }
        """
        if not request.packages:
            raise NotSupportedError('No packages in shipment.')

        results = Queue()
        for carrier in self.carriers.values():
            threading.Thread(
                target=_task, args=(carrier, request, results)).start()

        return dict((results.get() for i in range(len(self.carriers))))

    def get_all_services(self):
        """
        Get all service options from all carriers.
        """
        for carrier in self.carriers.values():
            for service in carrier.get_all_services():
                yield service

    def get_service(self, carrier_name, service_id):
        for key in self.carriers:
            if key == carrier_name:
                return self.carriers[key].get_service(service_id)
        raise NotSupportedError()

    def get_package_type(self, carrier_name, type_id):
        for key in self.carriers:
            ### if no carrier specified, check all carriers
            if not carrier_name or key == carrier_name:
                try:
                    return self.carriers[key].get_package_type(type_id)
                except NotSupportedError:
                    continue
        raise NotSupportedError()

    def get_all_package_types(self):
        """
        Returns all types of containers supported by all carriers. Specifying
        something other than the generic customer-supplied package/softpak
        will yield limited rates results because most package types are
        carrier-specific.
        """
        return set(itertools.chain(*(
            carrier.get_all_package_types()
            for carrier in self.carriers.values()
        )))


def _task(carrier, request, results):
    data_dict = {'services': None, 'error': None}
    try:
        data_dict['services'] = carrier.get_services(request)
    except Exception as err:
        if not hasattr(err, 'traceback'):
            err.traceback = sys.exc_info()[2]
        data_dict['error'] = err

    results.put((carrier, data_dict))

