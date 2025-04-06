#!/usr/bin/env python3

from pwn import *
import random
import string
import os

os.environ["PWNLIB_NOTERM"] = "1"

def get_random_string(n, alph=string.ascii_letters+string.digits):
    return ''.join([random.choice(alph) for _ in range(n)])

class CatStorage:
    def __init__(self, target_ip) -> None:
        self.loggined = False
        self.target_ip = target_ip
        self.conn = self.remote_conn()
        self.wait_timeout = 10

    def remote_conn(self) -> remote:
        return remote(self.target_ip, 3000)

    def create_db(self) -> tuple[str, str]:
        if self.conn.connected() == False:
            raise Exception("Dropped connection")
        if self.loggined:
            raise Exception("Can't use no-login method when loggined")
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(b"1")
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        db_name = self.conn.recvline(timeout=self.wait_timeout).decode().strip()
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        token = self.conn.recvline(timeout=self.wait_timeout).decode().strip()
        self.loggined = True
        return db_name, token 

    def create_file(self, file_name:str, content:str):
        if self.loggined == False:
            raise Exception("Not loggined")
        if self.conn.connected() == False:
            raise Exception("Dropped connection")
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(b"2")
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(file_name.encode())
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(content.encode())

    def read_file(self, file_name:str):
        
        if self.loggined == False:
            raise Exception("Not loggined")
        if self.conn.connected() == False:
            raise Exception("Dropped connection")
        
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(b"1")
        b = self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(file_name.encode())
        a = self.conn.recvuntil(b":", timeout=self.wait_timeout)
        resp = self.conn.recvline(timeout=self.wait_timeout).decode().strip()
        resp = self.conn.recvline(timeout=self.wait_timeout).decode().strip()
        return resp

    
    def login(self, token:str):
        if self.conn.connected() == False:
            raise Exception("Dropped connection")
        if self.loggined:
            raise Exception("Can't use no-login method when loggined")
        
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(b"2")
        self.conn.recvuntil(b":", timeout=self.wait_timeout)
        self.conn.sendline(token.encode())
        self.loggined = True

            
    def close(self):
        if self.conn.connected():
            self.conn.close()
        self.loggined = False


def main():
    cat = CatStorage("team_to_attack_ip")
    # Here your exploit
    cat.close()

if __name__ == "__main__":
    main()
