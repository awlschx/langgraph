import operator
from typing import Annotated
from operator import add


class State:
    topic: str
    materials:str
    draft:str
    feedback:Annotated[list[str],add]
    round:int
    approved:bool
    doc_path:str


