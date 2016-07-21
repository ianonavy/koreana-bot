import json
import logging
import math
import re
import time
import threading

import arrow
import pandas
import slacker
from fuzzywuzzy import fuzz
from fuzzywuzzy import process
from slacksocket import SlackSocket

from koreana_bot.messages import MESSAGES


with open('default_config.json') as default_config_file:
    CONFIG = json.load(default_config_file)
with open('config.json') as config_file:
    CONFIG.update(json.load(config_file))


SLACK_ENABLED = True

slack = slacker.Slacker(CONFIG['slack-token'])

logger = logging.getLogger('koreana-bot')
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


PRICES = CONFIG['prices']
MENU_ITEMS = {item.lower(): item for item in PRICES}
for item in CONFIG['options']:
    for option in CONFIG['options'][item]:
        name, price_adjustment = option
        PRICES[item] += price_adjustment
        PRICES["{} - {}".format(item, name)] = PRICES[item]
    del PRICES[item]


def notify_slack(message):
    if not SLACK_ENABLED:
        return
    channel = "#{}".format(CONFIG['post-channel'])
    message = message.replace("@channel", "<!channel|@channel>")
    slack.chat.post_message(channel, message, as_user=True)


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

    # Dealing with people who say 'A' something but didn't mention 'Special A'
    # Calling .split() will separate on whitespace
    if 'a' in text.split() and 'special' not in text:
        return None
    if 'menu' in text:
        return None

    # Use simpler partial ratio with no full processing for better accuracy
    item, confidence = process.extractOne(
        text, MENU_ITEMS.keys(),
        lambda x: x,
        scorer=fuzz.partial_ratio)
    item = MENU_ITEMS[item]

    if confidence > CONFIG['min-confidence']:
        if item in CONFIG['options']:
            # Try exact match for options (to support hand roll vs roll)
            option_names = [name for name, _ in CONFIG['options'][item]]
            option_names = sorted(option_names, key=len, reverse=True)
            for option_name in option_names:
                if option_name in text:
                    option = option_name
                    option_confidence = 100
                    break
            else:
                option, option_confidence = process.extractOne(
                    text,
                    option_names,
                    lambda x: x,
                    scorer=fuzz.partial_ratio)
            item += " - " + option

            if user and option_confidence < CONFIG['min-confidence']:
                notify_slack(MESSAGES['option unsure'].format(user=user,
                                                              item=item,
                                                              option=option))
            if user:
                logger.debug('[%s%%] "%s" => %s (%s)', confidence, text,
                             item, get_user_name(user))
        return item
    else:
        return None


def fetch_messages():
    oldest_timestamp = int(time.time()) - CONFIG['initial-window-seconds']
    group_id, group_type = _get_group_or_channel_id(CONFIG['listen-channel'])
    res = getattr(slack, group_type).history(group_id,
                                             oldest=oldest_timestamp,
                                             count=1000)
    return reversed(res.body['messages'])


def _order_changed(orders, user, item):
    return user in orders and orders[user]['item'] != item


def add_orders(orders, messages):
    for message in messages:
        user = message['user']
        if user == CONFIG['bot-user-id']:
            continue
        item = get_item(message['text'], user)
        if item:
            name = get_user_name(user)
            if item == 'Cancel' and name in names:
                del orders[name]
                notify_slack(MESSAGES['cancelled'].format(user=user))
                continue
            orders[user] = {'name': name, 'item': item}
            if _order_changed(orders, user, item):
                notify_slack(MESSAGES['changed'].format(user=user, item=item))
            else:
                notify_order(orders, user)
    return orders


def get_costs(orders):
    order_list = sorted(orders.values(), key=lambda order: order['name'])
    columns = ['name', 'item']
    costs = pandas.DataFrame(order_list, columns=columns)
    costs['price'] = costs['item'].map(PRICES)
    costs['tax'] = costs['price'] * CONFIG['tax-rate']
    costs['tip'] = costs['price'] * CONFIG['tip-rate']
    costs['total'] = costs['price'] + costs['tax'] + costs['tip']
    return costs


def post_costs(costs):
    if costs.empty:
        message = MESSAGES['empty']
    else:
        message = "```{}```".format(costs.to_string(index=False,
                                                    justify='left'))
    notify_slack(message)


def pluralize(singular_string, quantity):
    plural_suffix = "es" if singular_string.endswith("s") else "s"
    return "{}{}".format(singular_string,
                         plural_suffix if quantity != 1 else "")


def is_a_la_carte(item):
    return (
        'Roll' in item or
        'Maki' in item or
        item.split(' - ')[0] in CONFIG['sushi-a-la-carte']
    )


def and_comma_join(items):
    if len(items) == 0:
        return ""
    elif len(items) == 2:
        return " and ".join(items)
    elif len(items) == 1:
        return items[0]
    else:
        items[-1] = "and " + items[-1]
        return ", ".join(items)


def get_full_order_message(quantities):
    message = ["Hi, I'd like to place a large order for pickup. "]
    non_sushi_items = []
    sushi_a_la_carte = []
    for index, (item, quantity) in enumerate(quantities.iteritems()):
        if is_a_la_carte(item):
            sushi_a_la_carte.append(
                "{} {} of {}".format(quantity,
                                     pluralize("order", quantity),
                                     item))
        else:
            # Pluralize the menu item, not the options
            parts = item.split(' - ')
            if len(parts) > 1:
                name = parts[0]
                options = ", ".join(parts[1:])
                pluralized_item = "{} with {}".format(
                    pluralize(name, quantity), options)
            else:
                pluralized_item = pluralize(item, quantity)

            non_sushi_items.append("{} {}".format(quantity, pluralized_item))
    message.append(and_comma_join(non_sushi_items))
    if sushi_a_la_carte:
        if len(non_sushi_items) > 0:
            message.append(". ")
        message.append("I'd also like to order some sushi a la carte. "
                       "I'd like ")
        message.append(and_comma_join(sushi_a_la_carte))
    message += ". That's it. Thank you!"
    return ''.join(message)


def countdown(orders):
    hour, minute = CONFIG['order-time'].split(':')
    deadline = arrow.now().replace(hour=int(hour),
                                   minute=int(minute))
    notify_slack(MESSAGES['welcome'].format(deadline=deadline.format("h:mma")))

    # add 1 to round up
    minutes_left = math.ceil((deadline - arrow.now()).total_seconds() / 60)
    while minutes_left > 0:
        if minutes_left in CONFIG['warning-minutes']:
            message_format = MESSAGES['n minutes warning']
            notify_slack(message_format.format(minutes=int(minutes_left)))

        if minutes_left == CONFIG['warning-minutes'][-1]:
            costs = get_costs(orders)
            notify_slack(MESSAGES['final changes'])
            post_costs(costs)
            notify_slack(MESSAGES['disclaimer'])

        time.sleep(60)
        minutes_left = math.ceil((deadline - arrow.now()).total_seconds() / 60)

    costs = get_costs(orders)

    notify_slack(MESSAGES['closed'])
    notify_final_order(costs=costs)


def notify_final_order(costs=None, orders=None):
    if costs is None:
        costs = get_costs(orders)
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


def notify_ordered(orders):
    message = ' '.join("<@{user}>".format(user=user) for user in orders)
    notify_slack(message)


def notify_order(orders, user):
    if user not in orders:
        message_format = MESSAGES['order missing']
        order = None
    else:
        message_format = MESSAGES['your order is']
        order = orders[user]['item']
    notify_slack(message_format.format(user=user, order=order))


def handle_event(orders, event):
    text = event['text']
    addressing_bot = '<@{}>:'.format(CONFIG['bot-user-id']) in text
    if re.search(r"what('| i)?s my order", text.lower()):
        notify_order(orders, event['user'])
    elif '@ordered' in text:
        notify_ordered(orders)
    elif addressing_bot and 'final order' in text:
        notify_final_order(orders=orders)
    elif addressing_bot and 'clear' in text:
        orders.clear()
        notify_slack(MESSAGES['cleared'])
    else:
        add_orders(orders, [event])


def main():
    global SLACK_ENABLED
    orders = {}
    logger.debug('Fetching historical messages')
    messages = fetch_messages()
    SLACK_ENABLED = False
    orders = add_orders(orders, messages)
    SLACK_ENABLED = True
    logger.debug('Got {} orders'.format(len(orders)))

    listen_group_id, _ = _get_group_or_channel_id(CONFIG['listen-channel'])
    started = False
    t = threading.Thread(target=countdown, args=(orders,))

    socket = SlackSocket(CONFIG['slack-token'], translate=False)
    for event in socket.events():
        if event.type != 'message':
            continue
        if event.event['channel'] != listen_group_id:
            continue
        if 'user' not in event.event or 'text' not in event.event:
            continue

        logger.debug(event.json)
        text = event.event['text']
        handle_event(orders, event.event)
        if 'start' in text and '<@{}>'.format(CONFIG['bot-user-id']) in text:
            if started:
                if t.is_alive():
                    notify_slack(MESSAGES['already started'])
                else:
                    # starting again
                    orders = {}
                    t = threading.Thread(target=countdown, args=(orders,))
                    t.start()
            else:
                t.start()
                started = True
