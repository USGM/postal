import inspect
import os

from suds.client import Client

base_path = os.path.split(os.path.abspath(inspect.getfile(inspect.currentframe())))[0]
full_path = os.path.join(base_path, 'ShipService_v13.wsdl')
url = "file://%s" % full_path
client = Client(url)
