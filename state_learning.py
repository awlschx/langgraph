#输入状态
from typing import TypedDict
from langgraph.graph import StateGraph, START, END



class InputState(TypedDict):
    username:str

#输出状态
class OutputState(TypedDict):
    graph_output:str


#全局状态
class OverAllState(TypedDict):
    username: str
    graph_output: str
    nickname:str

#私有状态
class PrivateState(TypedDict):
    greeting:str


#定义节点
def node1(state:InputState)->OverAllState:
    return {
        "nickname" : "Dear " + state["username"]
    }

def node2(state:OverAllState)->PrivateState:
    return {
        "greeting":"Hello, "+state["nickname"]
    }


def node3(state:PrivateState)->OutputState:
    return {
        "graph_output":state["greeting"]+"很高兴认识你"
    }

#构建图
builder = StateGraph(state_schema=OverAllState,
                     input_schema=InputState,
                     output_schema=OutputState)

#添加节点添加边
builder.add_node("node1",node1)
builder.add_node("node2",node2)
builder.add_node("node3",node3)

builder.add_edge(START,"node1")
builder.add_edge("node1","node2")
builder.add_edge("node2","node3")
builder.add_edge("node3",END)

graph = builder.compile()

result = graph.invoke({"username":"chx"})
print(result)





