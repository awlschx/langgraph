import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.types import interrupt

from myrepo.assistant.state import State
from myrepo.assistant.tool import find

if hasattr(sys.stdout,"reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(override=True)

model = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)
model_with_tools = model.bind_tools([find])
OUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

MAX_COUNT = 8
def search (state:State)->State:
    #根据topic返回materials
    topic = state["topic"]
    return {
        "topic":topic
    }


def draft (state:State) -> State:
    #调模型写草稿；模型觉得资料不够时，会先要求调 find 工具
    history = list(state["agent_message"])
    new_msgs = []

    #从 tool_node 回来的那一趟，最后一条是 ToolMessage：把工具结果交给模型接着写，
    #不能再重复发一遍需求，否则模型会一遍遍重复调工具
    if not history or not isinstance(history[-1], ToolMessage):
        lines = [f"主题：{state['topic']}"]
        if state["feedback"]:
            #不把上一轮意见带进来，每轮草稿都一模一样，循环永远不收敛
            lines.append(f"上一条修改意见（必须采纳）：{state['feedback'][-1]}")
        lines.append(f"请写第 {state['round'] + 1} 版草稿。资料不够就先用 find 查一次。")
        new_msgs.append(HumanMessage(content="\n".join(lines)))

    response = model_with_tools.invoke(history + new_msgs)
    new_msgs.append(response)

    update = {"agent_message": new_msgs}
    if not response.tool_calls:
        #只有模型真交出了草稿才算写了一版（中间那几趟只是去调工具）
        update["draft"] = response.content
        update["round"] = state["round"] + 1
    return update


def route_after_draft(state:State)->Literal["review", "tool_node"]:
    last = state["agent_message"][-1]
    return "tool_node" if last.tool_calls else "review"


tools = [find]
#进行审查，由人决定是否驳回
def review (state:State) -> State:
    response = interrupt({
        'draft':state["draft"],
        'round':state["round"],
        'history':state["feedback"]
    })
    #决定是回去draft还是放行
    if response["approved"]:
        return {
            "approved":True
        }
    else:
        return {
            "approved":False,
            "feedback":[response["comment"]]
        }

#路由函数
def route_after_review (state:State) -> Literal["finalize", "draft"]:
    if state["approved"]:
        return "finalize"
    if state["round"] >= MAX_COUNT:
        return "finalize"
    return "draft"


def finalize(state:State)->State:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bad = r'\/:*?"<>|'
    safe = "".join(c for c in state["topic"] if c not in bad).strip() or "untitled"
    path = OUT_DIR / f"{safe}.md"

    lines = [f"# {state['topic']}", "", state["draft"], ""]
    if state["feedback"]:
        lines += ["---", "", f"## 修订记录（共 {state['round']} 版）", ""]
        lines += [f"{i}. {f}" for i, f in enumerate(state["feedback"], 1)]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [finalize] {path}")          # 这是日志，不是界面
    return {"doc_path": str(path)}
