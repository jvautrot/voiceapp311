"""
City services in alerts dict:
    Street Cleaning
    Trash and recycling
    City building hours
    Parking meters
    Tow lot

Alerts for day are fetched from dictionary with city service as key


Example:

service_alerts['Street Cleaning'] = "Today is the third Tuesday of the month \\
and street cleaning is running on a normal schedule."

"""

from bs4 import BeautifulSoup
from urllib import request
from enum import Enum
from mycity.mycity_request_data_model import MyCityRequestDataModel
from mycity.mycity_response_data_model import MyCityResponseDataModel
import mycity.intents.speech_constants.get_alerts_intent as constants
import logging
import typing

logger = logging.getLogger(__name__)


class Services(Enum):
    """
    Organizes and contains information about all possible alert types
    that are supported in a readable format.

    """
    STREET_CLEANING = 'Street Cleaning'
    TRASH = 'Trash and recycling'
    CITY_BUILDING_HOURS = 'City building hours'
    PARKING_METERS = 'Parking meters'
    TOW_LOT = 'Tow lot'
    PUBLIC_TRANSIT = 'Public Transit'
    SCHOOLS = 'Schools'
    ALERT_HEADER = 'Alert header'


# constants for scraping boston.gov
BOSTON_GOV = "https://www.boston.gov"
SERVICE_NAMES = "cds-t t--upper t--sans m-b300"
SERVICE_INFO = "cds-d t--subinfo"
HEADER_1 = "t--upper t--sans lh--000 t--cb"
HEADER_2 = "str str--r m-v300"
HEADER_3 = "t--sans t--cb lh--000 m-b500"

ALERTS_INTENT_CARD_TITLE = "City Alerts"

TOW_LOT_NORMAL_MESSAGE = "The tow lot is open from 7 a.m. - 11 p.m. "
TOW_LOT_NORMAL_MESSAGE += "Automated kiosks are available 24 hours a day, "
TOW_LOT_NORMAL_MESSAGE += "seven days a week for vehicle releases."

# Strings we use to determine if there is snow related alert
SNOW_ALERT_QUERY = ["snow", "winter weather", "inclement weather"]


def get_alerts_intent(
        mycity_request: MyCityRequestDataModel,
        get_alerts_function_for_test: typing.Callable[[], typing.Dict] = None,
        prune_normal_responses_function_for_test:
        typing.Callable[[], typing.Dict] = None,
        alerts_to_speech_output_function_for_test:
        typing.Callable[[], typing.AnyStr] = None
) -> MyCityResponseDataModel:
    """
    Generate response object with information about citywide alerts

    :param mycity_request: MyCityRequestDataModel object
    :param get_alerts_function_for_test: Injectable function for unit tests
    :param prune_normal_responses_function_for_test: Injectable function
     for unit tests
    :param alerts_to_speech_output_function_for_test: Injectable function
    for unit tests
    :return: MyCityResponseDataModel object
    """
    logger.debug('MyCityRequestDataModel received:' +
                 mycity_request.get_logger_string())

    # get the intent_variables and sessions_attribute object from the request
    intent_variables = mycity_request.intent_variables
    session_attributes = mycity_request.session_attributes
    service_name = intent_variables['ServiceName'].get('value') \
        if 'ServiceName' in intent_variables else None
    session_alerts = session_attributes.get('alerts', get_pruned_alerts(
        get_alerts_function_for_test, prune_normal_responses_function_for_test))


    logger.debug('ServiceName: ' + str(service_name) +
                 ', session_alerts: ' + str(session_alerts))

    # Build the response.
    mycity_response = _create_response_object()
    mycity_response.session_attributes = session_attributes.copy()
    mycity_response.should_end_session = True

    if session_alerts is None:
        logger.debug(
            "Could not get alerts from session attributes or Boston webpage")
        mycity_response.should_end_session = False
        mycity_response.output_speech = constants.LAUNCH_REPROMPT_SPEECH
        return mycity_response

    if service_name is None:
        # If the user hasn't give us a service name, check if we should
        # list alerts if there are only a few, or ask the user to select one
        if len(session_alerts) > 1:
            mycity_response.session_attributes['alerts'] = session_alerts
            mycity_response.dialog_directive = "ElicitSlotServiceName"
            mycity_response.should_end_session = False
            mycity_response.output_speech = list_alerts_output(session_alerts)
        else:
            mycity_response.output_speech = \
                alerts_to_speech_output(session_alerts) \
                if alerts_to_speech_output_function_for_test is None \
                else alerts_to_speech_output_function_for_test(session_alerts)
    elif service_name == 'all':
        # Respond with all alert text
        mycity_response.output_speech = \
            alerts_to_speech_output(session_alerts) \
            if alerts_to_speech_output_function_for_test is None \
            else alerts_to_speech_output_function_for_test(session_alerts)
    elif service_name in session_alerts:
        # Grab the requested service alert
        alert = {service_name: session_alerts[service_name]}
        mycity_response.output_speech = alerts_to_speech_output(alert) \
            if alerts_to_speech_output_function_for_test is None \
            else alerts_to_speech_output_function_for_test(alert)
    else:
        # Service not found. Re-ask for the desired service.
        mycity_response.should_end_session = False
        mycity_response.output_speech = constants.INVALID_SERVICE_NAME_SCRIPT
        mycity_response.output_speech += list_alerts_output(session_alerts)
        mycity_response.dialog_directive = "ElicitSlotServiceName"

    return mycity_response


def get_pruned_alerts(get_alerts_function_for_test, prune_normal_responses_function_for_test):
    """
    Returns dictionary {service: alert text} alerts from the Boston webpage that are not in "normal" condition.

    :param get_alerts_function_for_test: Injectable function for unit tests
    :param prune_normal_responses_function_for_test: Injectable function for unit tests
    """
    alerts = get_alerts() if get_alerts_function_for_test is None \
        else get_alerts_function_for_test()
    logger.debug("[dictionary with alerts scraped from boston.gov]:\n" +
                 str(alerts))

    pruned_alerts = prune_normal_responses(alerts) \
        if prune_normal_responses_function_for_test is None \
        else prune_normal_responses_function_for_test(alerts)
    logger.debug("[dictionary after pruning]:\n" + str(pruned_alerts))
    pruned_alerts = {k.lower(): v for k, v in pruned_alerts.items()}
    return pruned_alerts


def get_inclement_weather_alert(
    mycity_request: MyCityRequestDataModel,
    get_alerts_function_for_test: typing.Callable[[], typing.Dict] = None,
) -> MyCityResponseDataModel:
    """
    Generates a response with information about any inclement weather alerts.

    :param mycity_request: MyCityRequestDataModel object
    :param get_alerts_function_for_test: Injectable function for unit tests
    :return: MyCityResponseDataModel object
    """
    logger.debug('MyCityRequestDataModel received:' +
                 mycity_request.get_logger_string())

    alerts = get_alerts() if get_alerts_function_for_test is None \
        else get_alerts_function_for_test()
    logger.debug("[dictionary with alerts scraped from boston.gov]:\n" +
                 str(alerts))

    logger.debug("filtering for inclement weather alerts")
    output_speech = constants.NO_INCLEMENT_WEATHER_ALERTS
    if Services.ALERT_HEADER.value in alerts:
        if any(query in alerts[Services.ALERT_HEADER.value].lower()
               for query in SNOW_ALERT_QUERY):
            logger.debug("inclement weather alert found")
            output_speech = alerts[Services.ALERT_HEADER.value]

    mycity_response = _create_response_object()
    mycity_response.session_attributes = mycity_request.session_attributes
    mycity_response.output_speech = output_speech
    mycity_response.should_end_session = True
    return mycity_response


def _create_response_object() -> MyCityResponseDataModel:
    """
    Creates a MyCityResponseDataModel populated with fields common
    to all city alerts

    :return: MyCityResponseDataModel
    """
    mycity_response = MyCityResponseDataModel()
    mycity_response.card_title = ALERTS_INTENT_CARD_TITLE
    mycity_response.reprompt_text = None
    mycity_response.should_end_session = True
    return mycity_response


def list_alerts_output(alerts: typing.Dict) -> typing.AnyStr:
    """
    Output list of alerts to pick for when there's multiple alerts.

    :param alerts: pruned alert dictionary
    :return: a string containing all alerts to decide on.
    """
    logger.debug('alerts: ' + str(alerts))
    alert_count = len(alerts)
    alert_list = ""
    for i, alert in enumerate(alerts.keys()):
        if i + 1 == alert_count:
            alert_list += 'and '
        alert_list += alert.capitalize()
        if i + 1 < alert_count:
            alert_list += ', '
    alert_list = alert_list.strip()
    return constants.ALERT_LISTING_SCRIPT.format(alert_count, alert_list)


def alerts_to_speech_output(alerts: typing.Dict) -> typing.AnyStr:
    """
    Checks whether the alert dictionary contains any entries. Returns a string
    that contains all alerts or a message that city services are operating
    normally.

    :param alerts: pruned alert dictionary
    :return: a string containing all alerts, or if no alerts are
        found, a message indicating there are no alerts at this time
    """
    logger.debug('alerts: ' + str(alerts))
    all_alerts = ""
    if Services.ALERT_HEADER.value in all_alerts:
        all_alerts += alerts.pop(Services.ALERT_HEADER.value)
    for alert in alerts.values():
        all_alerts += alert + ' '
    # this is a kludgy fix for the {'alert header': ''} bug
    if all_alerts.strip() == "":
        return constants.NO_ALERTS
    else:
        return all_alerts.rstrip()


def prune_normal_responses(service_alerts: typing.Dict) -> typing.Dict:
    """
    Remove any text scraped from Boston.gov that aren't actually alerts.
    For example, parking meters, city building hours, and trash and
    recycling are described "as on a normal schedule"

    :param service_alerts: raw alerts dictionary, potentially with unrelated
        non-alert data
    :return: pruned alert dictionary containing only the current
        alert information
    """
    logger.debug('service_alerts: ' + str(service_alerts))


    # for any defined service, if its alert is that it's running normally,
    # remove it from the dictionary
    for service in Services:
        if service.value in service_alerts and \
                str.find(service_alerts[service.value], "normal") != -1:
            service_alerts.pop(service.value)                       # remove
    if service_alerts.get(Services.TOW_LOT.value) == TOW_LOT_NORMAL_MESSAGE:
        service_alerts.pop(Services.TOW_LOT.value)
    return service_alerts


def get_alerts():
    """
    Checks Boston.gov for alerts, and if present scrapes them and returns
    them as a dictionary

    :return: a dictionary that maps alert names to detailed alert message
    """
    logger.debug('')

    # get boston.gov as an httpResponse object
    url = request.urlopen(BOSTON_GOV)
    # feed the url object into beautiful soup
    soup = BeautifulSoup(url, "html.parser")
    url.close()

    # parse, sanitize returned strings, place in dictionary
    services = [s.text.strip() for s in soup.find_all(class_=SERVICE_NAMES)]
    service_info = [s_info.text.strip().replace(u'\xA0', u' ')
                    for s_info in soup.find_all(class_= SERVICE_INFO)]
    alerts = {}
    for i in range(len(services)):
        alerts[services[i]] = service_info[i]
    # get alert header, if any (this is something like "Winter Storm warning")
    header = ""
    if soup.find(class_= HEADER_1) is not None:
        header += soup.find(class_= HEADER_1).text + '. '
        header += soup.find(class_= HEADER_2).text + '. '
        header += soup.find(class_= HEADER_3).text + ' '
    # weird bug where a blank header was appended to dictionary. this should
    # prevent that
    if header != '':
        alerts[Services.ALERT_HEADER.value] = header.rstrip()
    return alerts
