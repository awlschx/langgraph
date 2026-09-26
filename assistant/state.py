import operator
from typing import Annotated, TypedDict
from operator import add

from langgraph.graph import add_messages


class State(TypedDict):
    topic: str
    materials:str
    draft:str
    feedback:Annotated[list[str],add]
    round:int
    approved:bool
    doc_path:str
    agent_message:Annotated[list, add_messages]

