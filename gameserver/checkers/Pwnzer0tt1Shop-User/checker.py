#!/usr/bin/env python3

import random
import string
import requests
import names
import checklib
from store_utils import *

data = checklib.get_data()
action = data["action"]
service_addr = data["host"]


def random_psw():
    return "".join(random.choices(string.ascii_letters + string.digits, k=24))


def check_sla():
    username = random_psw()
    password = random_psw()
    email = names.email_gen()
    user = register_user(username, password, email)

    test_donation = random.randint(1, 100)

    donate_user(test_donation)

    updated_user = user_info()

    if updated_user["wallet"] != user["wallet"] - test_donation:
        checklib.quit(checklib.Status.ERROR, "Wallet not updated correctly")

    if updated_user["username"] != username or updated_user["email"] != email:
        checklib.quit(checklib.Status.ERROR, "User data mismatch")

    logout_user()

    token_login(user["token"])

    checklib.quit(checklib.Status.OK)


def put_flag():
    flag = data["flag"]

    username = random_psw()
    password = random_psw()
    email = flag
    flag_user = register_user(username, password, email)
    flag_user["password"] = password

    checklib.save_flag_data(flag, flag_user)
    checklib.post_flag_id({"username": username})

    checklib.quit(checklib.Status.OK)


def get_flag():
    flag = data["flag"]
    user = checklib.get_flag_data(flag)

    user_data = login_user(user["username"], user["password"])
    if user_data["email"] != flag:
        checklib.quit(checklib.Status.ERROR, "Flag mismatch")

    logout_user()

    user_data = token_login(user["token"])

    if user_data["email"] != flag:
        checklib.quit(checklib.Status.ERROR, "Flag mismatch")

    checklib.quit(checklib.Status.OK)


def main():
    try:
        if action == checklib.Action.CHECK_SLA.name:
            check_sla()
        elif action == checklib.Action.PUT_FLAG.name:
            put_flag()
        elif action == checklib.Action.GET_FLAG.name:
            get_flag()
    except (requests.RequestException, requests.HTTPError) as e:
        checklib.quit(checklib.Status.DOWN, "Request error", str(e))
    except KeyError:
        checklib.quit(checklib.Status.ERROR, "Unexpected response")


if __name__ == "__main__":
    main()
