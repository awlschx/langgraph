import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# tool.py 有可能比 node.py 先执行完，所以这里也要自己读一遍 .env，
# 否则下面建客户端时 os.getenv 还拿不到 key
load_dotenv()

# 这个工具自己也要调模型，所以单独建一个客户端。
# 不能从 node.py 里 import —— node.py 反过来要 import 这个 find，会成环。
_search_model = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)


@tool
def find(keyword: str) -> str:
    """按关键词搜集资料，返回两三句话的摘要。已有资料不够时，可以换个关键词再查一次。"""
    res = _search_model.invoke([
        SystemMessage(content="针对关键词搜集资料，用两到三句话概括，不要展开。"),
        HumanMessage(content=keyword),
    ])
    return res.content
