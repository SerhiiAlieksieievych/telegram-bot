import telebot
import re
import json
import requests
import codecs
import time
from telebot import types

token = "token"
bot = telebot.TeleBot(token)

class CurrencyData:
    def __init__(self):
        self.fileObj = codecs.open("currencies.json", "r", "utf_8_sig")
        self.text = self.fileObj.read()
        self.fileObj.close()
        self.currency_codes_data = json.loads(self.text)
        self.inversed_currency_codes_data = {}
        for i in self.currency_codes_data:
            self.inversed_currency_codes_data.update({self.currency_codes_data[i]['ISOnum']: i})

    def getCurrencyCodes(self):
        return self.currency_codes_data

    def getInversedCurrencyCodes(self):
        return self.inversed_currency_codes_data


class Currency:
    def __init__(self, demonym, currency_codes_data):
        self.demonym = demonym
        self.ISOnum = currency_codes_data[demonym]
        self.name = currency_codes_data[demonym]["name"]
        self.rateToUah = None
        self.rateToUsd = None


class RequestToMonobank:
    def __init__(self):
        self.count_of_requests = 0
        self.currencyA = None
        self.currencyB = None
        self.monobank_data = None
        self.monobank_currency_codes = [980]
        self.rateBuy = None
        self.rateSell = None
        self.rateCross = None
        self.succesed = False

    def set_currencies(self, currencyA, currencyB):
        self.currencyA = currencyA
        self.currencyB = currencyB

    def _request_to_monobank(self):
        self.succesed = False
        resp = requests.get("https://api.monobank.ua/bank/currency")
        if resp.status_code == 200:
            self.monobank_data = json.loads(resp.text)
            for i in self.monobank_data:
                self.monobank_currency_codes.append(i['currencyCodeA'])
                self.succesed = True
                self.count_of_requests = 0
        elif self.count_of_requests <= 3:
            time.sleep(2.5)
            self.count_of_requests += 1
            self._request_to_monobank()

    def get_monobank_currency_codes(self):
        self._request_to_monobank()
        if self.succesed:
            return self.monobank_currency_codes

    def get_value_of_currencies(self):
        self._request_to_monobank()
        if self.succesed:
            if self.currencyA.ISOnum['ISOnum'] == 840:
                self.currencyA.rateToUah = self.monobank_data[0]['rateSell']
            elif self.currencyB.ISOnum['ISOnum'] == 840:
                self.currencyB.rateToUah = self.monobank_data[0]['rateBuy']
            elif self.currencyA.ISOnum['ISOnum'] == 978:
                self.currencyA.rateToUah = self.monobank_data[1]['rateSell']
            elif self.currencyB.ISOnum['ISOnum'] == 978:
                self.currencyB.rateToUah = self.monobank_data[1]['rateBuy']
            if self.currencyA.ISOnum['ISOnum'] == 978 and self.currencyB.ISOnum['ISOnum'] == 840:
                self.currencyA.rateToUsd = self.monobank_data[2]['rateSell']
                return (self.currencyA, self.currencyB)
            elif self.currencyA.ISOnum['ISOnum'] == 840 and self.currencyB.ISOnum['ISOnum'] == 978:
                self.currencyB.rateToUsd = self.monobank_data[2]['rateBuy']
                return (self.currencyA, self.currencyB)
            else:
                for i in self.monobank_data:
                    if not self.currencyA.rateToUah and i['currencyCodeA'] == self.currencyA.ISOnum['ISOnum']:
                        self.currencyA.rateToUah = i['rateCross']
                    if not self.currencyB.rateToUah and i['currencyCodeA'] == self.currencyB.ISOnum['ISOnum']:
                        self.currencyB.rateToUah = i['rateCross']
                return (self.currencyA, self.currencyB)


class CurrencyConverter:
    def __init__(self, currencies: tuple[object, object], amount: int):
        self.currencyA = currencies[0]
        self.currencyB = currencies[1]
        self.amount = amount
        self.amountInUah = None
        self.result = None

    def get_result_of_conversion(self):
        if self.currencyA.ISOnum['ISOnum'] == 978 and self.currencyB.ISOnum['ISOnum'] == 840:
            self.result = self.amount * self.currencyA.rateToUsd
        elif self.currencyA.ISOnum['ISOnum'] == 840 and self.currencyB.ISOnum['ISOnum'] == 978:
            self.result = self.amount / self.currencyB.rateToUsd
        elif self.currencyB.ISOnum['ISOnum'] == 980:
            self.result = self.amount * self.currencyA.rateToUah
        elif self.currencyA.ISOnum['ISOnum'] == 980:
            self.result = self.amount / self.currencyB.rateToUah
        else:
            self.amountInUah = self.amount * self.currencyA.rateToUah
            self.result = self.amountInUah / self.currencyB.rateToUah
        return self.result


class RequestsStorage:
    def __init__(self):
        self.requests = []
        self.FILE_NAME = 'requests.json'

    def set_request(self, user_id, init_cur, targ_cur, amount, result):
        request_info = {
            "user": f"{user_id}",
            "initial_currency": f"{init_cur.ISOnum}",
            "target_currency": f"{targ_cur.ISOnum}",
            "amount": f"{amount}",
            "result": f"{result}"
        }
        self.requests.append(request_info)
        if len(self.requests) > 10: self.requests.pop(0)

    def save_json(self):
        json_string = json.dumps(self.requests, indent=4)
        requests_file = open(self.FILE_NAME, 'w')
        requests_file.write(json_string)
        requests_file.close()


class BotHandler:
    def __init__(self):
        self.requests_storage = RequestsStorage()
        self.user_id = None
        self.users_input = None
        self.message = None
        self.castom_ban_list = []
        self.currency_data = CurrencyData()
        self.currency_codes_data = CurrencyData().getCurrencyCodes()
        self.monobank_currency_codes = None
        self.amount = None
        self.initial_currency = None
        self.initial_currency_name = None
        self.target_currency = None
        self.greeting_phrase = "Здоровенькі були!\n"
        self.offer_phrase = """Введіть суму та демонім вашої валюти у форматі:
    <СУМА ДЕМОНІМ_ВАЛЮТИ>
Наприклад:
    100000 USD"""

    def set_initial_currency(self, name_of_currency):
        self.initial_currency = Currency(name_of_currency, self.currency_codes_data)

    def set_target_currency(self, name_of_currency):
        self.target_currency = Currency(name_of_currency, self.currency_codes_data)

    def check_pattern(self):
        if not re.fullmatch(r'\d+\s([A-Za-z]{3})', self.users_input):
            bot.send_message(self.message.chat.id, "НЕВІРНИЙ ФОРМАТ ВВОДУ! СПРОБУЙТЕ ЩЕ РАЗ!\n" + self.offer_phrase)
            bot.register_next_step_handler(self.message, self.string_handler)
            return False
        else:
            return True

    def check_amount(self, tested_amount: int):
        if tested_amount <= 0:
            bot.send_message(self.message.chat.id, "Неправильно вказана сума!\n" + self.offer_phrase)
            bot.register_next_step_handler(self.message, self.string_handler)
            return False
        else:
            return True

    def check_for_pork(self, demonym: str):
        if demonym == "RUB":
            bot.send_message(self.message.chat.id,
                             f"Монобанк не опрацьовує це сміття!\n" + "Спробуйте піти в слід за кораблем!")
            self.castom_ban_list.append(self.user_id)
            return False
        else:
            return True

    def check_demonym(self, demonym):
        try:
            if self.currency_codes_data[demonym]['ISOnum'] not in self.monobank_currency_codes:
                bot.send_message(self.message.chat.id,
                                 f"Монобанк не опрацьовує {self.currency_codes_data[demonym]['name']}\n" + self.offer_phrase)
                bot.register_next_step_handler(self.message, self.string_handler)
                return False
            else:
                return True
        except KeyError:
            bot.send_message(self.message.chat.id, "Неправильно вказан демонім валюти!\n" + self.offer_phrase)
            bot.register_next_step_handler(self.message, self.string_handler)
            return False

    def check_validity(self):
        """If input is valid sets amount and initial currancy demonym, and returns True, else returns False"""
        if self.check_pattern():
            _list_for_handling = self.users_input.split(' ')
            demonym = _list_for_handling[1].upper()
            amount = int(_list_for_handling[0])
            if self.check_amount(amount) and self.check_for_pork(demonym) and self.check_demonym(demonym):
                self.amount = amount
                self.initial_currency_name = demonym
                return True
        return False

    def keyboard_creator(self):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("USD", callback_data="USD")
        btn2 = types.InlineKeyboardButton("EUR", callback_data="EUR")
        btn3 = types.InlineKeyboardButton("UAH", callback_data="UAH")
        btn4 = types.InlineKeyboardButton("Інша валюта", callback_data="else")
        if self.currency_codes_data[self.initial_currency_name]['ISOnum'] == 980:
            markup.add(btn1, btn2, btn4)
        elif self.currency_codes_data[self.initial_currency_name]['ISOnum'] == 978:
            markup.add(btn1, btn3, btn4)
        else:
            markup.add(btn2, btn3, btn4)
        return markup

    def string_handler(self, message):
        self.message = message
        self.user_id = message.from_user.id
        self.users_input = message.text.strip()
        if message.text == '/start':
            start(message)
            return
        if not self.check_validity(): return
        markup = self.keyboard_creator()
        bot.send_message(message.chat.id, "Оберіть потрібну валюту", reply_markup=markup)

    def restart(self, message):
        bot.send_message(message.chat.id, self.offer_phrase)
        bot.register_next_step_handler(message, bot_handler.string_handler)


bot_handler = BotHandler()


@bot.message_handler(commands=['start'])
def start(message):
    conversion_request = RequestToMonobank()
    bot_handler.monobank_currency_codes = conversion_request.get_monobank_currency_codes()
    if bot_handler.user_id not in bot_handler.castom_ban_list:
        if bot_handler.monobank_currency_codes:
            bot.send_message(message.chat.id, bot_handler.greeting_phrase)
            bot.send_message(message.chat.id, bot_handler.offer_phrase)
            bot.register_next_step_handler(message, bot_handler.string_handler)
        else:
            btn_restart = types.InlineKeyboardButton("Спробувати ще раз", callback_data="restart")
            markup = types.InlineKeyboardMarkup(row_width=2).add(btn_restart)
            bot.send_message(message.chat.id, "Сервер Монобанку не надав дані. Спробуйте скористатися ботом пізніше",
                             reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Тікай з села!")


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot_handler.set_initial_currency(bot_handler.initial_currency_name)
    message, data = call.message, call.data
    bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.message_id)
    if data == 'restart':
        bot_handler.restart(message)
        return
    if data == 'finish':
        bot.send_message(message.chat.id, "Най щастить!")
        return
    if data == 'btn_get_requests_data':
        bot_handler.requests_storage.save_json()
        bot.send_message(message.chat.id, "Інформація про останні 10 запитів:\n")
        bot.send_document(message.chat.id, open(rf'./{bot_handler.requests_storage.FILE_NAME}', 'rb'))
        btn_restart = types.InlineKeyboardButton("Так", callback_data="restart")
        btn_finish = types.InlineKeyboardButton("Ні", callback_data="finish")
        markup = types.InlineKeyboardMarkup(row_width=2).add(btn_restart, btn_finish)
        bot.send_message(message.chat.id, "Зробити ще одну конвертацію?", reply_markup=markup)
        return
    if data != 'else':
        bot.send_message(message.chat.id, f"{data}")
        bot_handler.set_target_currency(data)
        conversion_request = RequestToMonobank()
        conversion_request.set_currencies(bot_handler.initial_currency, bot_handler.target_currency)
        conversion_data = conversion_request.get_value_of_currencies()
        if conversion_data:
            result = CurrencyConverter(conversion_data, bot_handler.amount).get_result_of_conversion()
            bot_handler.requests_storage.set_request(bot_handler.user_id, bot_handler.initial_currency,
                                                     bot_handler.target_currency, bot_handler.amount, result)
            bot.send_message(message.chat.id,
                             f"{bot_handler.amount} {bot_handler.initial_currency.name} = {"{:.2f}".format(result)} {bot_handler.target_currency.name}")
            btn_restart = types.InlineKeyboardButton("Так", callback_data="restart")
            btn_finish = types.InlineKeyboardButton("Ні", callback_data="finish")
            btn_get_requests_data = types.InlineKeyboardButton("Отримати інформацію про останні 10 запитів",
                                                               callback_data="btn_get_requests_data")
            markup = types.InlineKeyboardMarkup(row_width=2).add(btn_restart, btn_finish, btn_get_requests_data)
            bot.send_message(message.chat.id, "Зробити ще одну конвертацію?", reply_markup=markup)
        else:
            btn_restart = types.InlineKeyboardButton("Спробувати ще раз", callback_data="restart")
            markup = types.InlineKeyboardMarkup(row_width=2).add(btn_restart)
            bot.send_message(message.chat.id, "Сервер Монобанку не надав дані. Спробуйте скористатися ботом пізніше",
                             reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup(row_width=3)
        btns = []
        for i in bot_handler.monobank_currency_codes:
            if i == bot_handler.initial_currency.ISOnum: continue
            btns.append(types.InlineKeyboardButton(bot_handler.currency_data.inversed_currency_codes_data[i],
                                                   callback_data=bot_handler.currency_data.inversed_currency_codes_data[
                                                       i]))
        markup.add(*btns)
        bot.send_message(message.chat.id, "Оберіть потрібну валюту", reply_markup=markup)
        return


bot.polling(none_stop=True)