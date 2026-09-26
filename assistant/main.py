

import sys

from langgraph.types import Command

# 要和 graph.py 里的包导入保持一致，所以从 lg_cource 目录跑：
#     python -m myrepo.assistant.main
from myrepo.assistant.graph import graph

# node.py 里改的是 stdout；stdin 不改的话，这里 input() 读到的中文会解码成乱码
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

#配一个固定id
config = {
    "configurable" :{
    "thread_id":"888"
}
}
#执行图
result = graph.invoke({"topic":input("请输入一个你感兴趣的主题"),"round":0},config=config)
while result.get("__interrupt__"):
    #获取interrupt中给用户展示的信息
    p = result["__interrupt__"][0].value
    print(f"第{p['round']}版：{p['draft']}")
    answer = input("通过？(y 或输入修改意见): ")
    decision = {"approved": True} if answer == "y" else {"approved": False, "comment": answer}
    result = graph.invoke(Command(resume=decision), config)

print(result["doc_path"])