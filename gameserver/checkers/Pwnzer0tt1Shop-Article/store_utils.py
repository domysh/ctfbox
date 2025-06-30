import checklib
import requests

data = checklib.get_data()
team_id = data["teamId"]
service_addr = "10.60." + team_id + ".1"

req = requests.Session()


def get_article(article_id: int):
    for article in get_article_list():
        if article["id"] == article_id:
            return article
    return None


def get_article_list():
    resp = req.get(f"http://{service_addr}:80/api/articles")
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad article list status code: {resp.status_code}"
        )
    return resp.json()


def register_user(username: str, password: str, email: str):
    user_data = {"username": username, "password": password, "email": email}
    resp = req.post(f"http://{service_addr}:80/api/register", json=user_data)
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad register status code: {resp.status_code}"
        )
    return resp.json()["user"]


def user_info():
    resp = req.get(f"http://{service_addr}:80/api/user")
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad user info status code: {resp.status_code}"
        )
    return resp.json()


def login_user(username: str, password: str):
    user_data = {"username": username, "password": password}
    resp = req.post(f"http://{service_addr}:80/api/login", json=user_data)
    if resp.status_code != 200:
        checklib.quit(checklib.Status.DOWN, f"Bad login status code: {resp.status_code}")
    return resp.json()["user"]


def donate_user(amount: int) -> str:
    donate_data = {"price": amount}
    resp = req.post(f"http://{service_addr}:80/api/donate", json=donate_data)
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad donate status code: {resp.status_code}"
        )
    return resp.json()["message"]


def shell_article(title: str, description: str, price: float, secret: str):
    shell_data = {
        "title": title,
        "description": description,
        "price": price,
        "secret": secret,
    }
    resp = req.post(f"http://{service_addr}:80/api/sell", json=shell_data)
    if resp.status_code != 200 and resp.status_code != 201:
        checklib.quit(checklib.Status.DOWN, f"Bad sell status code: {resp.status_code}")
    return resp.json()["article"]


def buy_article(article_id: int) -> bool:
    resp = req.post(f"http://{service_addr}:80/api/store/{article_id}/buy")
    if resp.status_code == 400:
        return False
    if resp.status_code != 200:
        checklib.quit(checklib.Status.DOWN, f"Bad buy status code: {resp.status_code}")
    return True


def logout_user() -> str:
    resp = req.post(f"http://{service_addr}:80/api/logout")
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad logout status code: {resp.status_code}"
        )
    return resp.json()["message"]


def token_login(token: str):
    token_data = {"token": token}
    resp = req.post(f"http://{service_addr}:80/api/login/token", json=token_data)
    if resp.status_code != 200:
        checklib.quit(
            checklib.Status.DOWN, f"Bad token login status code: {resp.status_code}"
        )
    return resp.json()["user"]
