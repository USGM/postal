from datetime import datetime
from time import timezone
from dateutil.relativedelta import relativedelta

from ..constructor import load_template, populate_template


def create_header(site_id, password):
    template = load_template('dhl', 'header.xml')
    return populate_template(template, {
        'site_id': site_id, 'password': password})


def enumerate_pieces(request):
    result = []
    template = load_template('dhl', 'piece.xml')
    for number, package in enumerate(request.packages):
        result.append(populate_template(
            template, {
                'length': package.length, 'width': package.width,
                'height': package.height, 'weight': package.weight,
                'number': number + 1}))
    return ''.join(result)


def money_snippet(template_name, request):
    template = load_template('dhl', template_name)
    money = None
    for package in request.packages:
        if not package.declarations:
            continue
        for declaration in package.declarations:
            if not money:
                money = declaration.value
            else:
                money += declaration.value
    if not money:
        return ''
    return populate_template(
        template, {
            'currency': money.currency, 'value': money.amount})


def rates_request(request, request_header, pieces, dutiable, duties):
    request_template = load_template('dhl', 'rates.xml')
    envelope_template = load_template('dhl', 'main.xml')
    ship_datetime = request.ship_datetime or datetime.now()
    ship_date = ship_datetime.strftime('%Y-%m-%d')
    hour = ship_datetime.hour
    minute = ship_datetime.minute
    if request.insure:
        insured = money_snippet('insured.xml', request)
    else:
        insured = ''
    offset = relativedelta(seconds=timezone)
    tz_hour = offset.hour or 0
    tz_min = offset.minute or 0
    if (tz_hour, tz_min) == (abs(tz_hour), abs(tz_min)):
        tz_sign = '+'
    else:
        tz_sign = '-'

    if dutiable:
        is_dutiable = 'Y'
    else:
        is_dutiable = 'N'
    tz_hour = "%02d" % abs(tz_hour)
    tz_min = "%02d" % abs(tz_min)
    escape_variables = {
        'origin_country': request.origin.country.alpha2,
        'origin_postal_code': request.origin.postal_code,
        'ship_date': ship_date,
        'hour': hour,
        'minute': minute,
        'is_dutiable': is_dutiable,
        'destination_country': request.destination.country.alpha2,
        'destination_postal_code': request.destination.postal_code,
        'tz_sign': tz_sign,
        'tz_hour': tz_hour,
        'tz_min': tz_min}
    non_escape_variables = {
        'duties': duties,
        'pieces': pieces,
        'request_header': request_header,
        'insured': insured}
    service_request = populate_template(
        request_template, escape_variables, non_escape_variables)
    return populate_template(
        envelope_template, {}, {
            'service_request': service_request})