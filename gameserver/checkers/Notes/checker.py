#!/usr/bin/env python3

import hashlib
import random
import string

import requests
import bs4

import names

import checklib

data = checklib.get_data()
action = data['action']
service_addr = data['host']

def create_note(title: str, content: str, private: bool) -> str:
    note_data = {}
    note_data['title'] = title
    note_data['content'] = content
    if private:
        note_data['private'] = ''

    resp = requests.post(f'http://{service_addr}:8000/new', data=note_data)
    if resp.status_code != 200:
        checklib.quit(checklib.Status.DOWN,
                    f'Bad create note status code: {resp.status_code}')

    parts = resp.url.split('/view/')
    if len(parts) != 2:
        checklib.quit(checklib.Status.DOWN, 'Invalid create note redirect')

    return parts[1].strip()


def view_note(note_id: str) -> tuple[str, str]:
    resp = requests.get(f'http://{service_addr}:8000/view/{note_id}')
    if resp.status_code != 200:
        checklib.quit(checklib.Status.DOWN,
                    f'Bad view note status code: {resp.status_code}')

    html = bs4.BeautifulSoup(resp.text, features="html.parser")
    title_elem = html.select_one('div.container > h1')
    content_elem = html.select_one('div.container > p')
    uuid_elem = html.select_one('div.container > small')
    if not title_elem or not content_elem or not uuid_elem:
        checklib.quit(checklib.Status.DOWN, 'Invalid view note page')

    return title_elem.text.strip(), content_elem.text.strip(), uuid_elem.text.strip()

def check_sla():

    resp = requests.get(f'http://{service_addr}:8000')
    if resp.status_code != 200:
        checklib.quit(checklib.Status.DOWN,
                    f'Bad index page status code: {resp.status_code}')

    note_title = names.get_random_name()
    note_content = ''.join(random.choices(
        string.ascii_letters + string.digits, k=64))
    note_id = create_note(note_title, note_content, False)

    view_note_title, view_note_content, view_note_uuid = view_note(note_id)
    if view_note_title != note_title or view_note_content != note_content or not view_note_uuid:
        checklib.quit(checklib.Status.DOWN, 'Invalid note title or content')

    checklib.quit(checklib.Status.OK)


def put_flag():
    flag = data['flag']

    note_title = names.get_random_name()
    note_id = create_note(note_title, flag, True)
    uuid_str = view_note(note_id)[2]

    checklib.save_flag_data(flag, {'note_id': note_id, 'note_title': note_title})

    try:
        checklib.post_flag_id({ "note_uuid": uuid_str })
    except Exception as e:
        checklib.quit(checklib.Status.ERROR, "Checker error", str(e))
    checklib.quit(checklib.Status.OK)


def get_flag():
    flag = data['flag']
    note_id = checklib.get_flag_data(flag)['note_id']
    _, note_content, _ = view_note(note_id)
    if note_content != flag:
        checklib.quit(checklib.Status.DOWN, 'No flag in note content')

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


if __name__ == "__main__":
    main()
