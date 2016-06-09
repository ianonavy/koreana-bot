from koreana_bot import get_item


def test_doesnt_parse_when_not_confident():
    message = u'does someone want to volunteer to place the order? gene has lunch plans already'
    assert get_item(message) is None


def test_special_a_for_me_then_please():
    message = u'okay, Special A for me then please'
    assert 'Special A' in get_item(message)


def test_lunch_special_b_with_kimchi():
    message = u'Lunch special B, with kimchi por favor'
    assert 'Special B - kimchee' == get_item(message)


def test_question_special_a():
    message = u'can i have a special A?'
    assert 'Special A' in get_item(message)


def test_special_a_salad_instead_of_kimchi():
    message = u'Special A - salad instead of kimchi'
    assert 'Special A - salad' == get_item(message)


def test_instead_of_in_beginning():
    message = u'instead of kimchi, i want salad with my special A'
    assert 'Special A - salad' == get_item(message)


def test_special_a_please():
    message = u'special A, please!'
    assert 'Special A' in get_item(message)


def test_soft_tofu_chigae_with_beef():
    message = u'Soft tofu Jjigae with beef please!'
    assert 'Soft Tofu Chigae - beef' == get_item(message)


def test_change_of_order():
    message = u'CHANGE OF ORDER. Please scratch the Teriyaki. I\u2019m going to go yook gae jang'
    assert 'Yook Gae Jang' == get_item(message)


def test_special_a_plus_salad():
    message = u'Special A + salad, ty'
    assert 'Special A - salad' == get_item(message)


def test_can_i_get_mine_with_a_salad():
    message = u'can I get mine with a salad? (special A)'
    assert 'Special A - salad' == get_item(message)


def test_misspelled_yook_gae_jung():
    message = u'yook gae jang please'
    assert 'Yook Gae Jang' == get_item(message)


def test_cancel():
    messages = [
        'cancel my order',
        'cancel',
        'please cancel my order',
    ]
    for message in messages:
        assert 'Cancel' == get_item(message)


def test_pray_emoji():
    message = u':pray:'
    assert get_item(message) is None


def test_i_love_that_i_am_now_a_bot():
    message = u'i love that i am now a bot'
    assert get_item(message) is None


def test_lunch_special_menu():
    message = u'i only put stuff from the  special menu'
    assert get_item(message) is None
