"""
Front-end for the Postal Library.
"""
from copy import copy
from multiprocessing.pool import ThreadPool
import sys
from .exceptions import PostalError, NotSupportedError
from carriers import Carrier


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
        # Give carriers a back reference to the main postal object.
        configuration_dict['postal'] = self

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
                print 'with these args: ' + str(carrier_configs[name])
                raise

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
        for i, package in enumerate(request.packages, 1):
            if package.length < 0 or package.width < 0 or package.height < 0:
                if len(request.packages) == 1:
                    raise NotSupportedError('The dimensions of that package '
                                            'are invalid.')
                raise NotSupportedError('The dimensions of package #%s are '
                                        'invalid.' % i)

        thread_pool = ThreadPool(processes=len(self.carriers))

        result = dict(thread_pool.map(
            _task, [(carrier, request) for carrier in self.carriers.values()]))
        thread_pool.terminate()
        thread_pool.join()
        return result

    def get_all_services(self):
        """
        Get all service options from all carriers.
        """
        for carrier in self.carriers.values():
            for service in carrier.get_all_services():
                yield service

    def get_service(self, carrier_name, service_id):
        if carrier_name not in self.carriers:
            raise PostalError(
                "A carrier named '%s' does not exist." % carrier_name)
        return self.carriers[carrier_name].get_service(service_id)

    def get_package_type(self, carrier_name, code):
        if carrier_name:
            return self.carriers[carrier_name].get_package_type(code)
        else:
            return Carrier.generic_packaging_table[code]

    def get_all_package_types(self):
        """
        Returns all types of containers supported by all carriers.
        """
        for package_type in Carrier.get_generic_package_types():
            yield package_type
        for carrier in self.carriers.values():
            for package_type in carrier.get_all_package_types(generics=False):
                yield package_type

    def without(self, *args):
        """
        Creates and returns a shallow copy of this Postal instance except with
        its carriers table missing the carriers named by the specified
        argument list. For example, calling postal_instance.without('UPS')
        creates a new postal object with all previous carriers except UPS.
        """
        result = copy(self)
        result.carriers = copy(self.carriers)
        for arg in args:
            result.carriers.pop(arg, None)
        return result


def _task(arg_list):
    carrier, request = arg_list
    data_dict = {'services': None, 'error': None}
    try:
        data_dict['services'] = carrier.get_services(request)
    except Exception as err:
        if not hasattr(err, 'traceback'):
            err.traceback = sys.exc_info()[2]
        data_dict['error'] = err

    return carrier, data_dict
