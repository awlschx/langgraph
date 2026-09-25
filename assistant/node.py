from langgraph.types import interrupt, Command
from typing import Annotated, Literal, TypedDict


from myrepo.assistant.state import State
from myrepo.interrupt_demo import final
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

MAX_COUNT = 8
def search (state:State)->State:
    #根据topic返回materials
    topic = state["topic"]
    return {
        "topic":topic
    }


def draft (state:State) -> State:
    #形成初步版本
    round = state["round"]
    round = round + 1
    text = f"第{round}版  "
    last = state["feedback"][-1] if state["feedback"] else None
    if last:
        text  += f"采纳的意见{last}"
    return {
        'draft':last,
        'round':round
    }

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
