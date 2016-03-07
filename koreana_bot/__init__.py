import logging
import json
import time
import threading

import arrow
import pandas
import slacker
import adverplex.settings
from fuzzywuzzy import process
from slacksocket import SlackSocket


POST_CHANNEL = '#ian-test-group'
LISTEN_CHANNEL = 'ian-test-group'
GROUP_NAME = 'koreana-thursday'
BOT_USER_ID = 'U0QNJ680G'
WINDOW_SIZE_SECONDS = 86400 * 5
ORDER_TIME_MINUTES = 60
CONFIDENCE_THRESHOLD = 70
WARNING_MINUTES = [30, 15]
FINAL_WARNING = 5
TAX_RATE = 0.07
TIP_RATE = 0.10
settings = adverplex.settings.Settings()
SLACK_TOKEN = settings.value('koreana/slack', required=True)
slack = slacker.Slacker(SLACK_TOKEN)

logger = logging.getLogger('koreana-bot')
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

MESSAGES = {
    'welcome': (
        "Hey, @channel, it's Koreana Thursday! Please say your orders in this "
        "channel. One menu item per person (no ordering for other people!). "
        "Please remember to specify kimchee/salad where appropriate. "
        "To change order, simply say your new order and I'll disregard the "
        "rest. To cancel your order, say 'cancel my order.' Ordering closes "
        "at {deadline}. Enjoy!"
    ),
    'n minutes warning': (
        "@channel Order closing in {minutes} minutes!"
    ),
    'final changes': (
        "@channel Last call for final changes. Here's the order so far:"
    ),
    'disclaimer': (
        "Disclaimer: I only really know about lunch specials. If I missed "
        "your order, please notify the person who is actually placing the "
        "order!"
    ),
    'closed': (
        "@channel Here is the final order:"
    ),
    'total': (
        "The total comes out to ${subtotal:.2f} + ${tip:.2f} = "
        "${grand_total:.2f}."
    ),
    'place order': (
        "Please call Koreana at (617) 576-8661 with the following "
        " message: \n> {message}"
    ),
    'empty': (
        "Nothing. Really? No takers?"
    ),
    'no order': (
        "Sorry folks, it's not happening today!"
    ),
    'already started': (
        "We've already started!"
    ),
    'option unsure': (
        "<@{user}>: I'm assuming you want {option}. Say your order again if "
        "I'm wrong."
    ),
    'cancelled': (
        "<@{user}>: I cancelled your order"
    ),
    'changed': (
        "<@{user}>: I changed your order to \"{item}\""
    )
}

PRICES = {
    # Lunch Menu
    'Kimchee Chigae': 10,
    'Duenjang Chigae': 10,
    'Soft Tofu Chigae': 10,
    'Yook Gae Jang': 11,
    'Dumpling Ricecake Soup': 10,
    'Sa Gol U-gergy Gouk': 10,
    'Hwe De Bop': 13,
    'Special A': 11,
    'Special B': 10,
    'Galbi': 13,
    'Bulgogi': 10,
    'Salmon Teriyaki': 11,
    'Chicken Teriyaki': 10,
    'Vegetable Tempura': 10,
    'Sashimi': 13,
    'Sushi': 11,

    # Gary's special order
    'Gom Tang': 14,

    'Cancel': 0,
}
OPTIONS = {
    'Duenjang Chigae': ['beef', 'pork', 'seafood'],
    'Soft Tofu Chigae': ['beef', 'pork', 'seafood'],
    'Special A': ['kimchee', 'salad'],
    'Special B': ['kimchee', 'salad'],
    'Galbi': ['kimchee', 'salad'],
    'Bulgogi': ['kimchee', 'salad'],
    'Salmon Teriyaki': ['kimchee', 'salad'],
    'Chicken Teriyaki': ['kimchee', 'salad'],
    'Vegetable Tempura': ['kimchee', 'salad'],
}
MENU_ITEMS = {item.lower(): item for item in PRICES.keys()}
for item in PRICES.keys():
    if item in OPTIONS:
        for option in OPTIONS[item]:
            PRICES["{} - {}".format(item, option)] = PRICES[item]
        del PRICES[item]


def notify_slack(message):
    message = message.replace("@channel", "<!channel|@channel>")
    slack.chat.post_message(POST_CHANNEL, message, as_user=True)


def _filter_channels_by_name(name, channels):
    return [channel for channel in channels if channel['name'] == name]


def _get_group_or_channel_id(name):
    groups = slack.groups.list().body['groups']
    matching_objects = _filter_channels_by_name(name, groups)
    if matching_objects:
        group_type = 'groups'
    else:
        group_type = 'channels'
        channels = slack.channels.list().body['channels']
        matching_objects = _filter_channels_by_name(name, channels)

    if not matching_objects:
        error_format = 'Could not find group or channel for {}'
        raise RuntimeError(error_format.format(name))

    return matching_objects[0]['id'], group_type


def get_user_name(user_id):
    user = slack.users.info(user_id).body['user']
    return user['real_name'] or user['name']


def clean_text(text):
    text = text.lower()
    # @channel is too similar to cancel
    text = text.replace('channel', '')
    # remove common phrases not needed to increase confidence
    phrases = {
        'here', 'for me', 'please', 'por favor', 'pls', 'plz', 'lunch',
        'thanks', 'thx', 'thank you',
    }
    for phrase in phrases:
        text = text.replace(phrase, '')
    # common alternative spelling of kimchee doesn't match
    text = text.replace('kimchi', 'kimchee')

    # ignore everything after "instead of"
    if text.startswith('instead of'):
        text = text.split(',')[1]
    else:
        text = text.split('instead of')[0]
    return text


def get_item(text, user=None):
    text = clean_text(text)
    # direct message at someone else should be ignored
    if '<@' in text:
        return None

    item, confidence = process.extractOne(text, MENU_ITEMS.keys())
    item = MENU_ITEMS[item]
    if confidence > CONFIDENCE_THRESHOLD:
        if item in OPTIONS:
            option, option_confidence = process.extractOne(text, OPTIONS[item])
            item += " - " + option
            if user and option_confidence < CONFIDENCE_THRESHOLD:
                notify_slack(MESSAGES['option unsure'].format(user=user,
                                                              option=option))
        if user:
            logger.debug('[%s%%] "%s" => %s (%s)',
                         confidence, text, item, get_user_name(user))
        return item
    else:
        return None


def fetch_messages():
    oldest_timestamp = int(time.time()) - WINDOW_SIZE_SECONDS
    group_id, group_type = _get_group_or_channel_id(GROUP_NAME)
    res = getattr(slack, group_type).history(group_id, oldest=oldest_timestamp)
    return reversed(res.body['messages'])


def _order_changed(orders, name, item):
    return name in orders and orders[name]['item'] != item


def add_orders(orders, messages):
    for message in messages:
        user = message['user']
        item = get_item(message['text'], user)
        if item:
            name = get_user_name(user)
            if item == 'Cancel' and name in orders:
                del orders[name]
                notify_slack(MESSAGES['cancelled'].format(user=user))
                continue
            if _order_changed(orders, name, item):
                notify_slack(MESSAGES['changed'].format(user=user, item=item))
            orders[name] = {'name': name, 'item': item}
    return orders


def get_costs(orders):
    order_list = sorted(orders.values(), key=lambda order: order['name'])
    columns = ['name', 'item']
    costs = pandas.DataFrame(order_list, columns=columns)
    costs['price'] = costs['item'].map(PRICES)
    costs['tax'] = costs['price'] * TAX_RATE
    costs['tip'] = costs['price'] * TIP_RATE
    costs['total'] = costs['price'] + costs['tax'] + costs['tip']
    return costs


def post_costs(costs):
    if costs.empty:
        message = MESSAGES['empty']
    else:
        message = "```{}```".format(costs.to_string(index=False,
                                                    justify='left'))
    notify_slack(message)


def get_full_order_message(quantities):
    message = "Hi, I'd like to place a large order for pickup. "
    for index, (item, quantity) in enumerate(quantities.iteritems()):
        # Conditionally add comma separation
        if len(quantities) > 1:
            if index + 1 == len(quantities):
                message += ", and "
            elif index > 0:
                message += ", "

        # Pluralize the menu item, not the options
        plural = "s" if quantity != 1 else ""
        parts = item.split(' - ')
        if len(parts) > 1:
            name = parts[0]
            options = ", ".join(parts[1:])
            pluralized_item = "{}{} with {}".format(name, plural, options)
        else:
            pluralized_item = item + plural

        message += "{} {}".format(quantity, pluralized_item)
    message += ". That's it. Thank you!"
    return message


def countdown(orders):
    deadline = arrow.now().replace(minutes=ORDER_TIME_MINUTES).format("h:mma")
    notify_slack(MESSAGES['welcome'].format(deadline=deadline))

    for cur_min in range(ORDER_TIME_MINUTES):
        minutes_left = ORDER_TIME_MINUTES - cur_min

        if minutes_left in WARNING_MINUTES:
            message_format = MESSAGES['n minutes warning']
            notify_slack(message_format.format(minutes=minutes_left))

        if minutes_left == FINAL_WARNING:
            notify_slack(MESSAGES['n minutes warning'].format(minutes=5))
            costs = get_costs(orders)
            notify_slack(MESSAGES['final changes'])
            post_costs(costs)
            notify_slack(MESSAGES['disclaimer'])
        time.sleep(1)

    costs = get_costs(orders)

    notify_slack(MESSAGES['closed'])
    if costs.empty:
        notify_slack(MESSAGES['no order'])
    else:
        post_costs(costs)
        subtotal = (costs['price'] + costs['tax']).sum()
        tip = costs['tip'].sum()
        grand_total = costs['total'].sum()
        notify_slack(MESSAGES['total'].format(subtotal=subtotal, tip=tip,
                                              grand_total=grand_total))

        quantities = costs.groupby('item').size()
        message = get_full_order_message(quantities)
        notify_slack(MESSAGES['place order'].format(message=message))


def main():
    orders = {}

    # fetch historical
    # messages = fetch_messages()
    # orders = add_orders(orders, messages)

    listen_group_id, _ = _get_group_or_channel_id(LISTEN_CHANNEL)
    started = False
    t = threading.Thread(target=countdown, args=(orders,))

    socket = SlackSocket(SLACK_TOKEN, translate=False)
    for event in socket.events():
        if event.type != 'message':
            continue
        if event.event['channel'] != listen_group_id:
            continue
        if event.event['user'] == BOT_USER_ID:
            continue

        logger.debug(event.json)
        text = event.event['text']
        add_orders(orders, [event.event])
        if 'start' in text and '<@{}>'.format(BOT_USER_ID) in text:
            if started:
                if t.is_alive():
                    notify_slack(MESSAGES['already started'])
                else:
                    # starting again
                    t = threading.Thread(target=countdown, args=(orders,))
                    t.start()
            else:
                t.start()
                started = True
