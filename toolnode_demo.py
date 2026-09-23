"""
LangGraph ToolNode 最小 demo

核心就一句话：ToolNode 是一个"预制节点"，你给它一堆工具，
它负责读取上一条 AIMessage 里的 tool_calls，逐个执行，
再把结果包成 ToolMessage 追加回 messages 里。

阅读顺序：
    第 1 步  定义工具
    第 2 步  单独跑 ToolNode（先不管模型，手工喂一个 tool_call 进去）
    第 3 步  接进图里，让模型自己决定要不要调工具
"""

import json
import os
import sys

# Windows 控制台默认 GBK，不改的话中文会乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

# 把同目录 .env 里的键值对读进 os.environ，之后 os.getenv 才拿得到
load_dotenv()


# ============================================================
# 第 1 步：定义工具
#   @tool 装饰器的作用：把普通函数变成"模型能看懂"的 Tool 对象。
#   函数的类型注解 -> 参数 schema，函数的 docstring -> 工具描述，
#   这两样东西会一起发给模型，模型靠它们决定调不调、怎么调。
#   所以 docstring 一定要写清楚，它直接影响模型调不调这个工具。
# ============================================================

@tool
def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    fake_db = {"北京": "晴，25℃", "上海": "小雨，22℃", "广州": "多云，30℃"}
    return fake_db.get(city, f"查不到 {city} 的天气")


@tool
def add(a: int, b: int) -> int:
    """计算两个整数之和。"""
    return a + b


tools = [get_weather, add]

print("=" * 60)
print("【第 1 步】工具定义好了")
for t in tools:
    print(f"  名称: {t.name}")
    print(f"  描述: {t.description}")
    print(f"  参数: {t.args}")   # 由类型注解自动生成的 JSON Schema
print("=" * 60)


# ============================================================
# 第 2 步：单独跑 ToolNode
#   先不接模型，手工造一条带 tool_calls 的 AIMessage 喂进去，
#   看清楚 ToolNode 的「输入是什么、输出是什么」。
#
#   注意：ToolNode 不能直接 .invoke()，因为它内部需要图运行时
#   （runtime），只在编译后的图里才存在。所以下面套了一个
#   只有 3 行的迷你图，里面除了 ToolsNode 什么都没有。
# ============================================================

tool_node = ToolNode(tools)

mini = StateGraph(MessagesState)
mini.add_node("tools", tool_node)
mini.add_edge(START, "tools")
mini_graph = mini.compile()

# 这就是模型要调工具时，实际发出的那种消息
# （真实场景里由模型生成，这里我们手工写死，方便观察）
fake_ai_message = AIMessage(
    content="",                       # 要调工具时 content 常常是空的
    tool_calls=[
        {
            "name": "get_weather",
            "args": {"city": "北京"},
            "id": "call_001",         # 每次调用要有唯一 id
        }
    ],
)

print("\n【第 2 步】手工喂一条 tool_call 给 ToolNode")
print(f"  输入 messages[-1] = {fake_ai_message.tool_calls}")

result = mini_graph.invoke({"messages": [fake_ai_message]})

# 输出还是一个字典，里面多了几条 ToolMessage —— 这就是工具的执行结果
print("  输出 messages =")
for m in result["messages"]:
    if isinstance(m, ToolMessage):
        print(f"    [新增] ToolMessage  name={m.name}  "
              f"tool_call_id={m.tool_call_id}  content={m.content}")
    else:
        print(f"    [{type(m).__name__}] （原来的那条，没被改动）")
print("  要点：ToolMessage 靠 tool_call_id 和那条 AIMessage 配对，")
print("        所以模型能知道「这个结果对应我哪一次调用」。")
print("=" * 60)


# ============================================================
# 第 3 步：接进图里
#   结构是最经典的 ReAct 循环：
#       START -> agent -> (tools_condition 判断) -> tools -> agent -> ...
#
#   tools_condition 是配套的路由函数，逻辑很简单：
#       最后一条消息里有 tool_calls    -> 返回 "tools"
#       没有（说明模型给出最终答复了）-> 返回 END
# ============================================================

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("没读到 DEEPSEEK_API_KEY，检查一下同目录下的 .env 文件")

model = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=API_KEY,
    temperature=0,
)

# bind_tools：把工具清单"告诉"模型。
# 注意这只是让模型知道有哪些工具，模型本身不执行工具，执行是 ToolNode 干的。
model_with_tools = model.bind_tools(tools)


def agent_node(state: MessagesState):
    """模型节点：读全部历史消息，产出下一条 AIMessage（可能是答复，也可能是 tool_calls）"""
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}


builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)                      # ToolNode 直接当节点用
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)   # 分叉：去 tools 还是结束
builder.add_edge("tools", "agent")                        # 工具跑完，回到模型看结果
graph = builder.compile()

print("\n【第 3 步】图的连线")
print(graph.get_graph().draw_mermaid())
print("=" * 60)


def run(question: str):
    print(f"\n>>> 用户: {question}")
    for chunk in graph.stream(
        {"messages": [{"role": "user", "content": question}]},
        stream_mode="updates",          # 每个节点跑完就吐一次，方便观察流程
    ):
        # chunk 形如 {"节点名": {"messages": [...]}}
        for node_name, update in chunk.items():
            print(f"  [节点 {node_name}]")
            for msg in update["messages"]:
                if isinstance(msg, ToolMessage):
                    print(f"      tools  -> {msg.name} 返回: {msg.content}")
                elif msg.tool_calls:
                    for tc in msg.tool_calls:
                        args = json.dumps(tc["args"], ensure_ascii=False)
                        print(f"      agent  -> 决定调用: {tc['name']}({args})")
                else:
                    print(f"      agent  -> 最终答复: {msg.content}")


if __name__ == "__main__":
    run("北京今天天气怎么样？")
    run("帮我算一下 123 + 456 等于多少")
    run("北京和上海的温度相差多少度？")   # 需要连续调两次工具，能看出循环
