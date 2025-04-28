#!/usr/bin/env python3

from pwn import remote, context
import checklib
import random
import string
import os

os.environ["PWNLIB_NOTERM"] = "1"

context.timeout = 5
context.log_level = "error"
context.log_level = "debug"

port = 3000
data = checklib.get_data()
action = data['action']
team_addr = data['host']
wait_timeout = 5

def get_random_string(n, alph=string.ascii_letters+string.digits):
    return ''.join([random.choice(alph) for _ in range(n)])

class LegolizeChecker:
    def __init__(self) -> None:
        self.logged_in = False
        self.username = None
        self.password = None
        self.token = None
        self.conn = self.remote_conn()

    def remote_conn(self) -> remote:
        try:
            r = remote(team_addr, port)
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot connect", str(e))
        return r

    def register(self) -> tuple[str, str]:
        if self.conn.connected() is False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        if self.logged_in:
            checklib.quit(checklib.Status.ERROR, "Already logged in")
        try:
            self.username = get_random_string(random.randint(8, 12))
            self.password = get_random_string(random.randint(8, 12))
            
            self.conn.recvuntil(b">", timeout=wait_timeout)
            self.conn.sendline(f"register {self.username} {self.password}".encode())
            response = self.conn.recvline_startswith(b"[CLI]", timeout=wait_timeout).decode()
            
            if "Registration successful" not in response:
                checklib.quit(checklib.Status.DOWN, "Registration failed")
                
            self.login(self.username, self.password)
            return self.username, self.password
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot register", str(e))

    def login(self, username, password):
        if self.conn.connected() is False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        if self.logged_in:
            checklib.quit(checklib.Status.ERROR, "Already logged in")
        try:
            self.conn.recvuntil(b">", timeout=wait_timeout)
            self.conn.sendline(f"login {username} {password}".encode())
            response = self.conn.recvline_startswith(b"[CLI]", timeout=wait_timeout).decode()
            
            if "Login successful" not in response:
                checklib.quit(checklib.Status.DOWN, "Login failed")
            
            self.token = response.split("Token: ")[-1].strip()    
            self.username = username
            self.password = password
            self.logged_in = True
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot login", str(e))
    
    def add_wish(self, wish_text):
        if not self.logged_in:
            checklib.quit(checklib.Status.ERROR, "Not logged in")
        if self.conn.connected() is False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        try:
            self.conn.recvuntil(b">", timeout=wait_timeout)
            self.conn.sendline(f"add_wish {wish_text}".encode())
            
            response = self.conn.recvline_startswith(b"[CLI]", timeout=wait_timeout).decode()
                     
            if "Entry added/updated" not in response:
                checklib.quit(checklib.Status.DOWN, "Failed to add wish")
                
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot add wish", str(e))
    
    def get_wish(self, token=None):
        if self.conn.connected() is False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        try:
            self.conn.recvuntil(b">", timeout=wait_timeout)
            if token is not None:
                self.conn.sendline(f"get_wish {token}".encode())
            else:
                self.conn.sendline(b"get_wish")
            
            # Modificato per catturare la risposta corretta dal nuovo formato
            self.conn.recvuntil(b"[Server] Wish for", timeout=wait_timeout)
            response = self.conn.recvline(timeout=wait_timeout).decode()
            return response
            
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot get wish", str(e))
            
    def close(self):
        if self.conn.connected():
            self.conn.close()
        self.logged_in = False

def check_sla():
    # Test basic functionality
    lego = LegolizeChecker()
    username, password = lego.register()
    
    # Add a wish
    wish_content = get_random_string(32)
    lego.add_wish(wish_content)
    
    # Verifica immediata dopo l'aggiunta del desiderio
    response = lego.get_wish(lego.token)
    if wish_content not in response:
        checklib.quit(checklib.Status.DOWN, "Invalid wish content")
    
    lego.close()
    
    lego = LegolizeChecker()
    lego.login(username, password)
    if wish_content not in lego.get_wish():
        checklib.quit(checklib.Status.DOWN, "Invalid wish content")
    
    old_token = lego.token
    
    lego.close()
    
    lego = LegolizeChecker()
    if wish_content not in lego.get_wish(old_token):
        checklib.quit(checklib.Status.DOWN, "Invalid wish content")
    lego.close()
    
    checklib.quit(checklib.Status.OK)


def put_flag():
    flag = data['flag']
    
    lego = LegolizeChecker()
    username, password = lego.register()
    lego.add_wish(flag)
    lego.close()
    
    checklib.save_flag_data(flag, {"username": username, "password": password, "token": lego.token})
    
    try:
        checklib.post_flag_id({"username": username})
    except Exception as e:
        checklib.quit(checklib.Status.ERROR, "Checker error", str(e))

    checklib.quit(checklib.Status.OK)


def get_flag():
    flag = data['flag']
    
    flag_data = checklib.get_flag_data(flag)
    username = flag_data["username"]
    password = flag_data["password"]
    token = flag_data["token"]
    
    lego = LegolizeChecker()
    lego.login(username, password)
    
    response = lego.get_wish(token)
    lego.close()
    
    if flag not in response:
        checklib.quit(checklib.Status.DOWN, "Flag not found")
    else:
        checklib.quit(checklib.Status.OK)


def main():
    if action == checklib.Action.CHECK_SLA.name:
        check_sla()
    elif action == checklib.Action.PUT_FLAG.name:
        put_flag()
    elif action == checklib.Action.GET_FLAG.name:
        get_flag()


if __name__ == "__main__":
    main()
