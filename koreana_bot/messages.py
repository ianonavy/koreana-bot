
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
        "Last call for final changes. Here's the order so far:"
    ),
    'disclaimer': (
        "*Disclaimer:* I only really know about lunch specials and sushi "
        "a la carte orders. If I missed your order, please notify the "
        "person who is actually placing the order!"
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
        "message: \n> {message}"
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
        "<@{user}>: I heard \"{item}\", but I'm assuming you want {option}. "
        "Say your order again if I'm wrong."
    ),
    'cancelled': (
        "<@{user}>: I cancelled your order."
    ),
    'changed': (
        "<@{user}>: I changed your order to \"{item}\"."
    ),
    'your order is': (
        "<@{user}>: Your order is: {order}"
    ),
    'order missing': (
        "<@{user}>: I don't have an order for you."
    ),
    'cleared': (
        "Cleared all orders."
    ),
}