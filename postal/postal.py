"""
Front-end for the Postal Library.
"""

import threading
from Queue import Queue
import sys
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
            self.carriers[name] = carrier(
                postal_configuration=configuration_dict,
                **carrier_configs[name])

    def options_async(self, request):
        if not request.packages:
            try:
                raise NotSupportedError('No packages in shipment.')
            except Exception as err:
                err.traceback = sys.exc_info()[2]
                err.carrier = None
                yield err
                return

        results = Queue()
        for carrier in self.carriers.values():
            ### The implementation of this loop currently assumes that the
            ### caller will always want all of the generated data.

            def task(carrier):
                try:
                    for service, data in \
                            carrier.get_services(request).iteritems():

                        ### copy before modifying in case a carrier binding
                        ### does something odd
                        info = dict(data)

                        if 'service' in info:
                            ### Don't silently overwrite something that might
                            ### be important
                            raise PostalError()

                        info['service'] = service
                        results.put(info)

                except Exception as err:
                    if not hasattr(err, 'traceback'):
                        err.traceback = sys.exc_info()[2]
                    err.carrier = carrier
                    results.put(err)

                finally:
                    results.put(None)  # this carrier is done

            threading.Thread(target=task, args=(carrier,)).start()

        num_carriers_finished = 0
        while num_carriers_finished < len(self.carriers):
            result = results.get()
            if result is None:
                num_carriers_finished += 1
            else:
                yield result

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
        raise Exception()
