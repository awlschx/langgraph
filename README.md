# LangGraph 学习仓库

按课程逐个概念学习 LangGraph，最后用一个综合项目把知识点串起来。

- 各课 demo：每个文件聚焦**一个**概念，可以独立运行
- 综合项目：`assistant/`，把 State、条件边、循环、工具节点、中断、持久化全部用上

---

## 目录结构

```
.
├── state_learning.py        # 课：State —— 输入/输出/全局/私有 四种 schema
├── toolnode_demo.py         # 课：工具节点 —— ToolNode 三步递进演示
├── interrupt_demo.py        # 课：中断 —— interrupt / resume / 缺 checkpointer 的后果
│
├── assistant/               # 综合项目：资料整理助手
│   ├── DESIGN.md            #   设计文档（写代码时对照）
│   ├── state.py             #   State 定义
│   ├── node.py              #   四个节点 + 两个路由函数 + 模型初始化
│   ├── tool.py              #   find 工具
│   ├── graph.py             #   搭图
│   └── main.py              #   入口：跑流程、处理中断循环
│
└── outputs/                 # assistant 生成的文档（不该提交，见「已知问题」）
```

**约定**：单个练习脚本平铺在根目录；成型的项目放子目录。

---

## 环境准备

### 解释器

虚拟环境在 **`D:\python_code\lg_cource\.venv`**——注意它在仓库外面（上一层），不在仓库里。

依赖：

```
langgraph            1.2.12
langchain-core       1.6.4
langchain-openai     1.6.4
python-dotenv        1.2.3
ddgs                 9.16.0     # 备用：真实联网搜索
```

安装：

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install langgraph langchain-openai python-dotenv
```

### API key

项目根目录需要一个 `.env`（已在 `.gitignore` 里，不会提交）：

```
DEEPSEEK_API_KEY=sk-你的key
```

key 从环境变量 `ANTHROPIC_AUTH_TOKEN` 取，用它生成：

```bash
printf 'DEEPSEEK_API_KEY=%s\n' "$ANTHROPIC_AUTH_TOKEN" > .env
```

**哪些文件需要 key**：

| 文件 | 需要 key 吗 |
|---|---|
| `state_learning.py` | 不需要 |
| `interrupt_demo.py` | 不需要 |
| `toolnode_demo.py` | 需要（调模型决定调工具） |
| `assistant/*` | 需要 |

---

## 怎么运行

### 各课 demo

直接跑，工作目录随意：

```bash
./.venv/Scripts/python.exe state_learning.py
./.venv/Scripts/python.exe toolnode_demo.py
./.venv/Scripts/python.exe interrupt_demo.py
```

### 综合项目

**必须在 `lg_cource` 目录下用 `-m` 跑**，因为代码里用的是 `from myrepo.assistant.xxx import ...` 这种包导入：

```bash
cd /d/python_code/lg_cource
.venv/Scripts/python.exe -m myrepo.assistant.main
```

跑起来之后：

```
请输入一个你感兴趣的主题>  LangGraph 的中断机制
第1版：<草稿内容>
通过？(y 或输入修改意见): 太长了，只留要点
第2版：<按意见重写的草稿>
通过？(y 或输入修改意见): y
D:\python_code\lg_cource\myrepo\outputs\LangGraph 的中断机制.md
```

---

## 综合项目：资料整理助手

### 做什么

输入一个主题，产出经人工审核的资料文档。

### 流程图

```
         START  → [draft] ⇄ [tool_node]
                     ||
                  [review]  ← interrupt：人工审核
                     ↓
                [finalize] → END
            
```

**两个循环**：

1. `draft → tool_node → draft` —— 模型觉得资料不够就调 `find` 补充，够了才交草稿
2. `review → draft → review` —— 人工驳回后带意见重写，最多 `MAX_COUNT` 轮

### 节点契约

| 节点 | 读 | 返回 | 写在哪 |
|---|---|---|---|
| `draft` | `topic`, `feedback`, `agent_message` | `{"draft", "round", "agent_message"}` | `node.py` |
| `tool_node` | `agent_message` 里的 tool_calls | `{"agent_message": [ToolMessage]}` | `ToolNode` 预制，`graph.py` 里实例化 |
| `review` | `draft`, `round`, `feedback` | `{"approved"}` 或 `{"approved", "feedback"}` | `node.py` |
| `finalize` | `topic`, `draft`, `feedback`, `round` | `{"doc_path"}` | `node.py` |

### State 字段

```python
class State(TypedDict):
    topic: str
    draft: str
    feedback: Annotated[list[str], add]           # 累积，不覆盖
    round: int
    approved: bool
    doc_path: str
    agent_message: Annotated[list, add_messages]  # draft-agent 的内部对话
```

### 三个关键设计点

**① `agent_message` 必须有 `add_messages` reducer**

ToolNode 只返回**新增**的消息（`[ToolMessage]`）。没有 reducer 的话，这次返回值会把整个历史**覆盖掉**，模型的上下文就只剩一条孤零零的工具结果。

**② `draft` 要判断"这一趟是不是刚拿到工具结果"**

```python
if not history or not isinstance(history[-1], ToolMessage):
    new_msgs.append(HumanMessage(...))     # 只在"新的一版"才发需求
```

如果每趟都重发一遍需求，模型会**一遍遍重复调工具**，永远交不出草稿。

**③ `tool.py` 单独建模型客户端，不从 `node.py` 里 import**

`node.py` 要 import `tool.py` 里的 `find`，如果 `tool.py` 反过来 import `node.py` 的 model，就成环了。所以各自建一个客户端。

### 知识点覆盖

| 概念 | 落在哪 |
|---|---|
| State / 多 schema | `state.py`；`state_learning.py` 练过四种 |
| `reducer` | `feedback` 用 `operator.add` 累积意见 |
| 节点 + 边 | 四个节点 |
| 条件边 | `route_after_draft`（两路）、`route_after_review`（三路） |
| 循环 | 工具循环 + 审核驳回循环 |
| `@tool` + ToolNode | `find` + `ToolNode(tools, messages_key=...)` |
| `interrupt` + `Command(resume)` | `review` 节点 + `main.py` 的 while 循环 |
| checkpointer + thread_id | `InMemorySaver()` + 固定 `thread_id` |

### 分阶段状态

| 版本 | 内容 | 状态 |
|------|---|---|
| v1   | 纯骨架（直线跑通，不接模型不用工具） |
| v2   | `draft` 升级成带工具的 agent | **已完成** |

---

## 参考资料

- `assistant/DESIGN.md` —— 综合项目的设计文档，含更详细的节点契约、interrupt 数据形状、启动顺序
