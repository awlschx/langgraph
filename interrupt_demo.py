"""
LangGraph 中断（interrupt）最小 demo

一句话：interrupt() 在节点内部调用，让整张图当场停下来，把控制权交回给调用方；
等你下次带着答复再进来，图从停下的地方继续往下跑。

四个必须记牢的点：
    1. interrupt() 的【返回值】就是恢复时 Command(resume=...) 传进去的东西
       —— 这一点最容易绕晕，第 1、2 步专门演示
    2. 恢复时，节点是【从函数开头重新执行】的，不是从 interrupt() 那行接着跑
       —— 所以 interrupt() 之前的代码会跑两遍，副作用要小心，第 2 步有演示
    3. 编译时必须给 checkpointer，不然恢复时报错（第 3 步看报错原文）
    4. 每次调用都要带同一个 thread_id，checkpointer 靠它找回那条中断记录
"""

import sys
from typing import TypedDict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class State(TypedDict):
    topic: str       # 主题
    draft: str       # 草稿
    approved: bool   # 人工是否批准


# ============================================================
# 三个节点：自动生成草稿 -> 人工审批（在这里中断）-> 按决定收尾
# ============================================================

def write_draft(state: State):
    """节点一：自动生成草稿。"""
    draft = f"《{state['topic']}》的草稿内容"
    print(f"  [write_draft]   生成草稿：{draft}")
    return {"draft": draft}


def wait_approval(state: State):
    """节点二：在这里中断，把决定权交给图外面的人。"""
    # ↓ 注意这行：恢复时整个函数会从头再跑一遍，所以它会出现两次
    print("  [wait_approval] 进入节点（每次执行本节点都会打印这行）")

    decision = interrupt({
        "ask": "这份草稿可以发布吗？",
        "draft": state["draft"],
    })
    # ↑↑↑ 中断点 ↑↑↑
    #
    # 第一次执行到这里时这一行【不会返回】，整张图当场停住，
    # 已经跑过的 state 由 checkpointer 存下来。
    #
    # 等外面 Command(resume=xxx) 恢复时，LangGraph 把整个 wait_approval
    # 函数从头调用一遍；这一次 interrupt() 不再暂停，而是直接返回 xxx。
    # 所以 decision 就等于你 resume 传进来的东西。

    print(f"  [wait_approval] interrupt() 返回了：{decision!r}")
    return {"approved": decision}


def publish(state: State):
    """节点三：根据人工决定收尾。"""
    if state["approved"]:
        print(f"  [publish]       已发布：{state['draft']}")
    else:
        print("  [publish]       人工驳回，不发布")
    return {}


# ============================================================
# 搭图
# ============================================================

builder = StateGraph(State)
builder.add_node("write_draft", write_draft)
builder.add_node("wait_approval", wait_approval)
builder.add_node("publish", publish)
builder.add_edge(START, "write_draft")
builder.add_edge("write_draft", "wait_approval")
builder.add_edge("wait_approval", "publish")
builder.add_edge("publish", END)

# checkpointer：负责记住"跑到哪儿了、state 是什么"，是中断能恢复的前提
graph = builder.compile(checkpointer=InMemorySaver())

# thread_id 是这条执行线的身份标识，同一个 thread_id 才能接上同一次中断
config = {"configurable": {"thread_id": "demo-1"}}


# ============================================================
# 第 1 步：第一次调用 —— 一路跑到中断点然后停住
# ============================================================

print("=" * 62)
print("【第 1 步】第一次 invoke，图会停在 interrupt() 那一行")
print("=" * 62)

result = graph.invoke({"topic": "LangGraph 中断"}, config)

print(f"  返回值的 key：{list(result.keys())}")
print("  ↑ 注意没有 approved，也没有执行 publish —— 图确实停住了")
print()
print(f"  __interrupt__ = {result['__interrupt__']}")

# __interrupt__ 是个元组，取第一个元素的 .value，就是传给 interrupt() 的那个值
payload = result["__interrupt__"][0].value
print(f"  取出 .value = {payload}")
print("  ↑ 这就是 interrupt({...}) 里那个字典，原样送到了调用方手里，")
print("    实际项目中你在这里拿到它，生成表单/按钮给人看")


# ============================================================
# 第 2 步：恢复 —— 带上答复，从断点继续
# ============================================================

print()
print("=" * 62)
print("【第 2 步】用 Command(resume=...) 恢复")
print("=" * 62)

# resume 传什么，第 1 步里那个 decision 就是什么
final = graph.invoke(Command(resume=True), config)

print()
print(f"  最终 approved = {final['approved']}")
print()
print("  这里有两个现象要盯住：")
print("  ① [write_draft] 没有再次打印 —— 说明图是从断点续跑的，不是在重跑全图")
print("  ② [wait_approval] 进入节点 打印了两次 —— 因为恢复时这个节点")
print("     是【从函数开头重新执行】的，interrupt() 之前那句 print 也跟着重跑了")
print()
print("  第 ② 点就是 interrupt 的头号坑：如果 interrupt() 之前写了数据库、")
print("  发了请求、扣了钱，恢复时会通通再执行一遍。所以 interrupt() 最好")
print("  放在节点最前面，或者保证前面的代码是幂等的（重复执行也无害）。")


# ============================================================
# 第 3 步：立起对照 —— 不给 checkpointer 会怎样
# ============================================================

print()
print("=" * 62)
print("【第 3 步】对照：编译时不给 checkpointer")
print("=" * 62)

no_cp = (
    StateGraph(State)
    .add_node("write_draft", write_draft)
    .add_node("wait_approval", wait_approval)
    .add_node("publish", publish)
    .add_edge(START, "write_draft")
    .add_edge("write_draft", "wait_approval")
    .add_edge("wait_approval", "publish")
    .add_edge("publish", END)
    .compile()          # ← 故意不给 checkpointer
)

# thread_id 随便给，反正没东西被存下来
no_cp_config = {"configurable": {"thread_id": "demo-2"}}

print("  第一次 invoke（看起来完全正常，这才是最坑的地方）：")
r = no_cp.invoke({"topic": "试试"}, no_cp_config)
print(f"    照样停下了，返回值还是带着 __interrupt__：{list(r.keys())}")

print()
print("  现在尝试恢复：")
try:
    no_cp.invoke(Command(resume=True), no_cp_config)
except RuntimeError as e:
    print(f"    报错：{type(e).__name__}: {e}")
    print("    ↑ 报错发生在【恢复】这一刻，而不是中断那一刻。")
    print("      所以缺 checkpointer 的 bug 很容易拖到线上才被发现。")

print()
print("=" * 62)
