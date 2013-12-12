import logging

logger = logging.getLogger('pycountry.db')
logger.addHandler(logging.NullHandler())
del logger

from configuration_base import base_postal_configuration
from data import Address, Request, Package, Declaration, Shipment
from postal import Postal