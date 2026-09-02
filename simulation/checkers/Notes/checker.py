#!/usr/bin/env python3
"""Checker of the simulated Notes service.

Same three actions as any CTFBox checker: store a flag, read it back a few
rounds later, and verify the service is alive in between.
"""

import os
import random
import string
import sys

import requests

sys.path.append("..")
import checklib  # noqa: E402
from checklib import Action, Status, get_data, post_flag_id, quit  # noqa: E402

PORT = int(os.environ.get("SERVICE_PORT", "8000"))
TIMEOUT = 8


def rand(length=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def url(host, path):
    return f"http://{host}:{PORT}{path}"


def check_service(host):
    """Registers a user, stores a note and reads it back."""
    user, password = rand(), rand(16)
    try:
        response = requests.post(
            url(host, "/register"), json={"user": user, "password": password}, timeout=TIMEOUT
        )
        if response.status_code != 200:
            quit(Status.DOWN, "Cannot register", f"register returned {response.status_code}")

        title, content = rand(), rand(24)
        response = requests.post(
            url(host, "/notes"),
            json={"user": user, "password": password, "title": title, "content": content},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            quit(Status.DOWN, "Cannot store a note", f"notes returned {response.status_code}")
        note_id = response.json().get("id")
        if not note_id:
            quit(Status.ERROR, "The service did not return a note id", str(response.text))

        response = requests.get(
            url(host, f"/notes/{note_id}"),
            params={"user": user, "password": password},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            quit(Status.DOWN, "Cannot read a note back", f"read returned {response.status_code}")
        if response.json().get("content") != content:
            quit(Status.ERROR, "The service returned the wrong note", "content mismatch")
    except requests.exceptions.RequestException as exc:
        quit(Status.DOWN, "The service is not answering", str(exc))


def put_flag(host, flag):
    user, password = rand(), rand(16)
    try:
        response = requests.post(
            url(host, "/register"), json={"user": user, "password": password}, timeout=TIMEOUT
        )
        if response.status_code != 200:
            quit(Status.DOWN, "Cannot register", f"register returned {response.status_code}")

        response = requests.post(
            url(host, "/notes"),
            json={"user": user, "password": password, "title": "flag", "content": flag},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            quit(Status.DOWN, "Cannot store the flag", f"notes returned {response.status_code}")
        note_id = response.json().get("id")
        if not note_id:
            quit(Status.ERROR, "No note id came back", str(response.text))
    except requests.exceptions.RequestException as exc:
        quit(Status.DOWN, "The service is not answering", str(exc))

    # What an attacker is allowed to know, and what we need to find it again.
    post_flag_id({"user": user, "note_id": note_id})
    checklib.save_flag_data(flag, {"user": user, "password": password, "note_id": note_id})


def get_flag(host, flag):
    try:
        data = checklib.get_flag_data(flag)
    except Exception as exc:
        quit(Status.ERROR, "Checker state lost", f"cannot read back the flag data: {exc}")

    try:
        response = requests.get(
            url(host, f"/notes/{data['note_id']}"),
            params={"user": data["user"], "password": data["password"]},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        quit(Status.DOWN, "The service is not answering", str(exc))

    if response.status_code != 200:
        quit(Status.DOWN, "The flag is gone", f"read returned {response.status_code}")
    if response.json().get("content") != flag:
        quit(Status.ERROR, "The flag changed", "content mismatch")


def main():
    data = get_data()
    action, host = data["action"], data["host"]

    if action == Action.CHECK_SLA.name:
        check_service(host)
    elif action == Action.PUT_FLAG.name:
        put_flag(host, data["flag"])
    elif action == Action.GET_FLAG.name:
        get_flag(host, data["flag"])
    else:
        quit(Status.ERROR, "Unknown action", action)

    quit(Status.OK)


if __name__ == "__main__":
    main()
