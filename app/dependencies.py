from fastapi import Header

def get_actor(x_actor: str = Header(default="system")):
    return x_actor