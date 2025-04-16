#!/usr/bin/env python3

from pwn import *
import checklib
import random
import string
import os

os.environ["PWNLIB_NOTERM"] = "1"


context.timeout = 5
context.log_level = "error"


port = 3000
data = checklib.get_data()
action = data['action']
team_addr = data['host']
wait_timeout = 5

def get_random_string(n, alph=string.ascii_letters+string.digits):
    return ''.join([random.choice(alph) for _ in range(n)])

class CatStorage:
    def __init__(self) -> None:
        self.loggined = False
        self.conn = self.remote_conn()

    def remote_conn(self) -> remote:
        try:
            r = remote(team_addr, port)
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot connect", str(e))
        return r

    def create_db(self) -> tuple[str, str]:
        if self.conn.connected() == False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection", str(e))
        if self.loggined:
            checklib.quit(checklib.Status.ERROR, "Already loggined")
        try:
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(b"1")
            self.conn.recvuntil(b":", timeout=wait_timeout)
            db_name = self.conn.recvline(timeout=wait_timeout).decode().strip()
            self.conn.recvuntil(b":", timeout=wait_timeout)
            token = self.conn.recvline(timeout=wait_timeout).decode().strip()
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot create db", str(e))  
        self.loggined = True
        return db_name, token 

    def create_file(self, file_name:str, content:str):
        if self.loggined == False:
            checklib.quit(checklib.Status.ERROR, "Not loggined")
        if self.conn.connected() == False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        try:
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(b"2")
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(file_name.encode())
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(content.encode())
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot create file", str(e))
    
    def read_file(self, file_name:str):
        if self.loggined == False:
            checklib.quit(checklib.Status.ERROR, "Not loggined")
        if self.conn.connected() == False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        try:
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(b"1")
            b = self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(file_name.encode())
            a = self.conn.recvuntil(b":", timeout=wait_timeout)
            resp = self.conn.recvline(timeout=wait_timeout).decode().strip()
            resp = self.conn.recvline(timeout=wait_timeout).decode().strip()
            return resp
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot read file", str(e))
    
    def login(self, token:str):
        if self.conn.connected() == False:
            checklib.quit(checklib.Status.DOWN, "Dropped connection")
        if self.loggined:
            checklib.quit(checklib.Status.ERROR, "Already loggined")
        try:
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(b"2")
            self.conn.recvuntil(b":", timeout=wait_timeout)
            self.conn.sendline(token.encode())
            self.loggined = True
        except Exception as e:
            checklib.quit(checklib.Status.DOWN, "Cannot login", str(e))
            
    def close(self):
        if self.conn.connected():
            self.conn.close()
        self.loggined = False

def check_sla():
    cat = CatStorage()
    _, token = cat.create_db()
    filename = get_random_string(32)
    content = get_random_string(32)
    cat.create_file(filename, content)
    cat.close()
    
    cat = CatStorage()
    cat.login(token)
    resp = cat.read_file(filename)
    if not content in resp:
        checklib.quit(checklib.Status.DOWN, "Invalid file content")
    cat.close()
    checklib.quit(checklib.Status.OK)


def put_flag():
    flag = data['flag']
    
    file_name = get_random_string(random.randint(10, 16))
    content = flag
    cat = CatStorage()
    db_name, token = cat.create_db()
    cat.create_file(file_name, content)
    cat.close()
    
    checklib.save_flag_data(flag, {"db_name":db_name, "token":token, "file_name":file_name})
    
    try:
        checklib.post_flag_id({ "db_name":db_name, "filename": file_name })
    except Exception as e:
        checklib.quit(checklib.Status.ERROR, "Checker error", str(e))

    checklib.quit(checklib.Status.OK)


def get_flag():
    flag = data['flag']
    
    flag_data = checklib.get_flag_data(flag)
    
    cat = CatStorage()
    cat.login(flag_data["token"])
    resp = cat.read_file(flag_data["file_name"])
    cat.close()
    if not flag in resp:
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
