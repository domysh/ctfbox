#!/usr/bin/env python3

import random
import string
import requests
import names
import checklib
from store_utils import *

data = checklib.get_data()
action = data['action']
service_addr = data['host']

def random_psw():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=24))

def check_sla():
    username = random_psw()
    password = random_psw()
    email = names.email_gen()
    user = register_user(username, password, email)
    
    test_article_title = names.get_random_name()
    test_article_description = random_psw()
    test_article_price = random.randint(1, 100)
    test_article_secret = random_psw()
    
    added_article = shell_article(test_article_title, test_article_description, test_article_price, test_article_secret)
    
    article = get_article(added_article['id'])
    
    if article == None:
        checklib.quit(checklib.Status.ERROR, 'Added article not found')
    
    if article['title'] != test_article_title or article['description'] != test_article_description or article['price'] != test_article_price:
        checklib.quit(checklib.Status.ERROR, 'Article data mismatch')
    
    #Auth test
    logout_user()
    token_login(user['token'])
    logout_user()
    login_user(username, password)
    logout_user()
    
    username = random_psw()
    password = random_psw()
    email = names.email_gen()
    user = register_user(username, password, email)
    
    if not buy_article(added_article['id']):
        checklib.quit(checklib.Status.ERROR, 'Failed to buy article')
        
    updated_user = user_info()
    
    if updated_user['wallet'] != user['wallet'] - test_article_price:
        checklib.quit(checklib.Status.ERROR, 'Wallet not updated correctly')
        
    article = get_article(added_article['id'])
    if article['secret'] != test_article_secret:
        checklib.quit(checklib.Status.ERROR, 'Article secret mismatch')
    
    checklib.quit(checklib.Status.OK)



def put_flag():
    flag = data['flag']

    username = random_psw()
    password = random_psw()
    email = names.email_gen()
    flag_user = register_user(username, password, email)
    article = shell_article(names.get_random_name(), names.get_random_name(), random.randint(1000,1000000), flag)
    flag_user['password'] = password
    
    checklib.save_flag_data(flag, {
        'article': article,
        'user': flag_user
    })
    checklib.post_flag_id({ "article_id": article['id'] })
    
    checklib.quit(checklib.Status.OK)
    


def get_flag():
    flag = data['flag']
    flag_data = checklib.get_flag_data(flag)
    user = flag_data['user']
    article = flag_data['article']
    
    login_user(user['username'], user['password'])
    article = get_article(article['id'])
    
    if article == None:
        checklib.quit(checklib.Status.DOWN, 'Article not found')
    
    if article['secret'] != flag:
        checklib.quit(checklib.Status.DOWN, 'No flag in article secret')

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
        checklib.quit(checklib.Status.DOWN, 'Request error', str(e))
    except KeyError:
        checklib.quit(checklib.Status.ERROR, 'Unexpected response', str(e))


if __name__ == "__main__":
    main()
