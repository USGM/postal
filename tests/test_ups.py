__author__ = 'Nathan Everitt'

#import logging
#logging.basicConfig(level=logging.DEBUG)
#logging.getLogger('suds.transit').setLevel(logging.DEBUG)

from ..carriers import ups

ups.request_rate('Shop', '06', '04')

#ups.ship()
