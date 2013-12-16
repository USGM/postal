import threading
from Queue import Queue
import sys

"""
Front-end for the Postal Library.
"""


class Postal:
    def __init__(self, configuration_dict):
        """
        configuration_dict:{
            'enabled_carriers' -> [Carrier, ...],
            'default_currency' -> string:len=3 = currency code, like 'USD',
            'company_name' -> string,
            'carrier_inits' -> {
                string = name of carrier class without trailing 'Api' ->
                    kwargs = arguments for each carrier's constructor,
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

    def options(self, package):
        for carrier in self.carriers.values():
            for service, data in carrier.get_services(package).iteritems():

                ### copy before modifying in case a carrier binding does
                ### something odd
                result = dict(data)

                if 'service' in result:
                    ### Don't silently overwrite something that might
                    ### be important
                    raise Exception()

                result['service'] = service
                yield result

    def options_async(self, package):
        results = Queue()
        for carrier in self.carriers.values():
            ### The implementation of this loop currently assumes that the
            ### caller will always want all of the generated data.

            def callme(carrier):
                try:
                    for service, data in \
                            carrier.get_services(package).iteritems():

                        ### copy before modifying in case a carrier binding
                        ### does something odd
                        info = dict(data)

                        if 'service' in info:
                            ### Don't silently overwrite something that might
                            ### be important
                            raise Exception()

                        info['service'] = service
                        results.put(info)

                except Exception as err:
                    err.traceback = sys.exc_info()[2]
                    err.carrier = carrier
                    results.put(err)

                finally:
                    results.put(None)  # this carrier is done

            threading.Thread(target=callme, args=(carrier,)).start()

        num_carriers_finished = 0
        while num_carriers_finished < len(self.carriers):
            result = results.get()
            if result is None:
                num_carriers_finished += 1
            else:
                yield result
