from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from myrepo.assistant.node import draft, search, finalize, review, route_after_review, tools, route_after_draft
from myrepo.assistant.state import State

builder = StateGraph(state_schema=State)

#添加边
builder.add_node("search",search)
builder.add_node("draft",draft)
builder.add_node("finalize",finalize)
builder.add_node("review",review)
builder.add_node("tool_node", ToolNode(tools, messages_key="agent_message"))

builder.add_conditional_edges("draft", route_after_draft, ["tool_node", "review"])   # 改：原来 draft 直连 review
builder.add_edge("tool_node", "draft")
builder.add_edge(START,"search")
builder.add_edge("search","draft")
builder.add_conditional_edges("review",
                              route_after_review,
                              ["draft","finalize"])

graph = builder.compile(checkpointer=InMemorySaver())
