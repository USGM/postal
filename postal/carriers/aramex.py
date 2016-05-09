from multiprocessing.pool import ThreadPool

from suds.client import Client

from money import Money
from postal.carriers.base import Carrier, ClearEmpty
from postal.exceptions import CarrierError

from ..exceptions import PostalError
from copy import deepcopy


class AramexApi(Carrier):
    """
    Implements calls to the aramex api.
    """
    
    name = 'Aramex'
    
    _code_to_description = {
    'PDX' : 'Priority document express',
    'PPX': 'Priority parcel express',
    'PLX': 'Priority letter express',
    'DDX': 'Deferred document express',
    'DPX' : 'Deferred parcel express',
    'GDX': 'Ground document express',
    'GPX': 'Ground parcel express'                        
    }
    
    _product_group_to_description = {
        'EXP' : 'International shipment',
        'DOM' : 'Domestic shipment'                               
    }
    
    _service_code_to_description = {
    'COD' : 'Cash on delivery',
    'FIRST' : 'First delivery',
    'FRDOM' : 'Free domicile',
    'HFPU' : 'Hold for pickup',
    'NOON': 'Noon delivery',
    'SIG' : 'Signature required'
    }
    
    _min_max_estimates = {
    'PDX' : (1, 2),
    'PPX': (1, 2),
    'PLX': (1, 2),
    'DDX': (1, 2),
    'DPX' : (1, 2),
    'GDX': (1, 3),
    'GPX': (1, 3),
    }
    
    _carrier_error_codes = {
     'ERR61' : 'Failed to get rates',
     'ERR52' : 'Service not available'
    }

    _rate_client = None
    _priority_letter_limit = 1.10231
    carrier_error = None
    
    def create_client(self, wsdl_name):
        client = Client(
            self.service_url(wsdl_name), plugins=[ClearEmpty(), self.log_service],
            timeout=self.postal_configuration.get('timeout', None))
        
        return client
    
    def __init__(self, username, password, version, postal_configuration=None, account_number=None, account_pin=None):
        super(AramexApi, self).__init__(postal_configuration)
        self.postal_configuration = postal_configuration
        self.account_number = account_number
        self.account_pin = account_pin
        self.username = username
        self.password = password
        self.version = version
             
    def requested_shipment_details(self, request):
        api_request = self.rates_client.factory.create('RateCalculatorRequest')
        api_request.ClientInfo = self.client_info
        if not request.origin:
            request.origin = self.postal_configuration['shipper_address']
            
        self.set_address(api_request.OriginAddress, request.origin)
        self.set_address(api_request.DestinationAddress, request.destination)
        self.set_shipment_details(api_request.ShipmentDetails, request)
        return api_request
     
    @staticmethod 
    def set_address(target, postal_address):
        target.City = postal_address.city
        target.CountryCode = postal_address.country.alpha2
        target.PostCode = postal_address.postal_code
        lines = {'Line{}'.format(x + 1) : postal_address.street_lines[x]
                  for x in range(len(postal_address.street_lines))
        }
        
        target.StateOrProvinceCode = postal_address.subdivision
        for line, value in lines.items():
            setattr(target, line, value)
    
    def set_shipment_details(self, target, request):
        target.Dimensions = None
        target.ProductGroup = 'EXP'
        if not request.international():
            target.ProductGroup = 'DOM'
        
        target.ActualWeight.Unit = 'LB'
        target.ActualWeight.Value = request.total_weight()
        target.ChargeableWeight = target.ActualWeight
        target.PaymentType = 'P'
        target.NumberOfPieces = len(request.packages)
           
    def set_shipment_items (self, target, request):
        for package in request.packages:
            shipment_item = self.rates_client.factory.create('ShipmentItem')
            shipment_item.PackageType = ''
            shipment_item.Quantity = 1
            shipment_item.Weight = package.weight
            shipment_item.Comments = ''
            target.append(shipment_item)

    @property
    def client_info(self):
        client = self.rates_client.factory.create('ClientInfo')
        client.UserName = self.username
        client.Password = self.password
        client.Version = self.version
        if self.account_number:
            client.AccountNumber = self.account_number
            client.AccountEntity = ""
            client.AccountPin = ""
            client.AccountCountryCode = ""
        
        return client
    
    def service_call(self, func, *args, **kwargs):
        response = super(AramexApi, self).service_call(func, *args, **kwargs)
        if response.HasErrors:
            msg = ''
            for notification in response.Notifications.Notification:
                msg += '{}'.format(notification['Code']) + notification['Message'] + '.'
                raise CarrierError(msg, code=notification['Code'])
        
        return response
      
    def get_services(self, request):
        AramexApi.carrier_error = None
        requests = self.get_requests(request)       
        thread_pool = ThreadPool(processes=len(requests))
        results = thread_pool.map(self.get_request_rate, [api_request  for api_request in requests])
        thread_pool.terminate()
        thread_pool.join()
        
        if AramexApi.carrier_error:
            raise AramexApi.carrier_error
        
        final = {
            self.get_service(key): {
                'price': value,
                'delivery_datetime': None,
                'trackable': True
            } for response in results if response for key, value in response.items() 
        }
        return final 
    
    def get_request_rate(self, request):
        try:
            response = self.service_call(self.rates_client.service.CalculateRate, request.ClientInfo, request.Transaction,
            request.OriginAddress, request.DestinationAddress, request.ShipmentDetails
                )
            return { request.ShipmentDetails.ProductType: self.get_price_dict(response)}
        except CarrierError as e:
            if e.code not in self._carrier_error_codes:
                # These error codes mean that the product type is not available for this particular request 
                # so we just ignore it.
                AramexApi.carrier_error = e
            return None
        
    def get_price_dict(self, info):
        price = {}
        price['base_price'] = Money(info.TotalAmount.Value, info.TotalAmount.CurrencyCode)
        price['total'] = price['base_price']
        price['fees'] = Money(0, info.TotalAmount.CurrencyCode)
        
        return price
        
    def get_requests(self, request):
        requests = []
        flat_services = ['PDX', 'DDX', 'GDX']
        non_flat_services = ['PPX', 'DPX', 'GPX']
        api_request = self.requested_shipment_details(request)
        
        if request.documents_only:
            if request.total_weight() < self._priority_letter_limit:
                api_req = deepcopy(api_request)
                api_req.ShipmentDetails.ProductType = 'PLX'
                requests.append(api_req)
            for service in flat_services:
                api_req = deepcopy(api_request)
                api_req.ShipmentDetails.ProductType = service
                requests.append(api_req)

        for service in non_flat_services:
            api_req = deepcopy(api_request)
            api_req.ShipmentDetails.ProductType = service
            requests.append(api_req)
        
        return requests
                       
    @property
    def rates_client(self):
        if not self._rate_client:
            self._rate_client = self.create_client('rates.wsdl')
        
        return self._rate_client
