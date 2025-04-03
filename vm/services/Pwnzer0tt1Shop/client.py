
import requests

class PwnShopClient:
    
    def __init__(self, service_addr) -> None:
        self.service_addr = service_addr
        self.req = requests.Session()

    def get_article(self, article_id: int):
        for article in self.get_article_list():
            if article['id'] == article_id:
                return article
        return None

    def get_article_list(self):
        resp = self.req.get(f'http://{self.service_addr}:80/api/articles')
        if resp.status_code != 200:
            raise Exception(f'Bad article list status code: {resp.status_code}')
        return resp.json()

    def register_user(self, username: str, password: str, email:str):
        user_data = {
            'username': username,
            'password': password,
            'email': email
        }
        resp = self.req.post(f'http://{self.service_addr}:80/api/register', json=user_data)
        if resp.status_code != 200:
            raise Exception(f'Bad register status code: {resp.status_code}')
        return resp.json()['user']

    def user_info(self):
        resp = self.req.get(f'http://{self.service_addr}:80/api/user')
        if resp.status_code != 200:
            raise Exception(f'Bad user info status code: {resp.status_code}')
        return resp.json()

    def login_user(self, username: str, password: str):
        user_data = {
            'username': username,
            'password': password
        }
        resp = self.req.post(f'http://{self.service_addr}:80/api/login', json=user_data)
        if resp.status_code != 200:
            raise Exception(f'Bad login status code: {resp.status_code}')
        return resp.json()['user']

    def donate_user(self, amount: int) -> str:
        donate_data = {
            'price': amount
        }
        resp = self.req.post(f'http://{self.service_addr}:80/api/donate', json=donate_data)
        if resp.status_code != 200:
            raise Exception(f'Bad donate status code: {resp.status_code}')
        return resp.json()['message']

    def shell_article(self, title: str, description: str, price: float, secret: str):
        shell_data = {
            'title': title,
            'description': description,
            'price': price,
            'secret': secret
        }
        resp = self.req.post(f'http://{self.service_addr}:80/api/sell', json=shell_data)
        if resp.status_code != 200 and resp.status_code != 201:
            raise Exception(f'Bad sell status code: {resp.status_code}')
        return resp.json()['article']

    def buy_article(self, article_id: int) -> bool:
        resp = self.req.post(f'http://{self.service_addr}:80/api/store/{article_id}/buy')
        if resp.status_code == 400:
            return False
        if resp.status_code != 200:
            raise Exception(f'Bad buy status code: {resp.status_code}')
        return True

    def logout_user(self) -> str:
        resp = self.req.post(f'http://{self.service_addr}:80/api/logout')
        if resp.status_code != 200:
            raise Exception(f'Bad logout status code: {resp.status_code}')
        return resp.json()['message']

    def token_login(self, token: str):
        token_data = {
            'token': token
        }
        resp = self.req.post(f'http://{self.service_addr}:80/api/login/token', json=token_data)
        if resp.status_code != 200:
            raise Exception(f'Bad token login status code: {resp.status_code}')
        return resp.json()['user']

