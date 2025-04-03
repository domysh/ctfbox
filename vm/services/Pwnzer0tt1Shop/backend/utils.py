
from config import TOKEN_SECRET
import math, random
import os, fasteners
from flask import session
from db import User
from werkzeug.exceptions import HTTPException

log_lock = fasteners.InterProcessLock(os.path.join(os.path.dirname(__file__), 'log.lock'))

def create_token(text: str) -> str:
    token_len = len(TOKEN_SECRET)
    text = (text * math.ceil(token_len / len(text)))[:token_len]
    result = bytes([ord(a) ^ ord(b) for a, b in zip(TOKEN_SECRET, text)])
    return result.hex()

class UserUnauthenticated(HTTPException):
    code = 401
    description = 'User not authenticated'

def get_logged_user() -> User:
    if 'user_id' not in session:
        session.clear()
        raise UserUnauthenticated()
    user = User.query.filter_by(id=session['user_id']).first()
    if user is None:
        session.clear()
        raise UserUnauthenticated()
    return user

def encode_with_words(s, seed):
    words = ["apple", "banana", "cat", "dog", "elephant", "fox", "grape", "hat", 
             "igloo", "jelly", "kite", "lemon", "monkey", "nest", "octopus", 
             "penguin", "queen", "rabbit", "sun", "tree", "umbrella", "violet", 
             "whale", "xray", "yacht", "zebra"]
    letters_for_numbers = list("abcdefghij")
    random.seed(seed)
    random.shuffle(words)
    random.shuffle(letters_for_numbers)
    
    char_map = {chr(i): word for i, word in zip(range(97, 123), words)}
    number_map = {str(i): letter for i, letter in zip(range(10), letters_for_numbers)}
    
    result = []
    for char in s.lower():
        if char in char_map: 
            result.append(char_map[char])
        elif char in number_map:
            result.append(number_map[char])
        else:
            result.append(char)
    return ' '.join(result)