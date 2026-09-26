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
START → [search] → [draft] ⇄ [tool_node]
                     │
              route_after_draft
                     │
                  [review]  ← interrupt：人工审核
                     │
              route_after_review
                ┌────┴────┐
            approved    round >= MAX_COUNT
                └────┬────┘
                     ↓
                [finalize] → END
                     │
                  (驳回时回到 draft)
```

**两个循环**：

1. `draft → tool_node → draft` —— 模型觉得资料不够就调 `find` 补充，够了才交草稿
2. `review → draft → review` —— 人工驳回后带意见重写，最多 `MAX_COUNT` 轮

### 节点契约

| 节点 | 读 | 返回 | 写在哪 |
|---|---|---|---|
| `search` | `topic` | `{"topic": ...}` | 目前是空转，见「已知问题」 |
| `draft` | `topic`, `feedback`, `agent_message` | `{"draft", "round", "agent_message"}` | `node.py` |
| `tool_node` | `agent_message` 里的 tool_calls | `{"agent_message": [ToolMessage]}` | `ToolNode` 预制，`graph.py` 里实例化 |
| `review` | `draft`, `round`, `feedback` | `{"approved"}` 或 `{"approved", "feedback"}` | `node.py` |
| `finalize` | `topic`, `draft`, `feedback`, `round` | `{"doc_path"}` | `node.py` |

### State 字段

```python
class State(TypedDict):
    topic: str
    materials: str                                # 目前没人消费，见「已知问题」
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
|---|---|---|
| v1 | 纯骨架（直线跑通，不接模型不用工具） | 已跳过，直接做了 v3 |
| v2 | `search` 换真实检索 | **未做**——目前 `find` 是用模型「模拟」搜索 |
| v3 | `draft` 升级成带工具的 agent | **已完成** |

---

## 已知问题 / 待办

按重要性排：

1. **`outputs/` 没有进 `.gitignore`，而且 `outputs/ai.md` 已经被提交了。** 生成产物不该进仓库。
   处理：`.gitignore` 加一行 `outputs/`，然后 `git rm --cached outputs/ai.md`。

2. **`find` 不是真检索。** 现在它是「再调一次模型，让它就关键词写两三句摘要」——看着像资料，其实还是模型凭训练数据编的。真要联网：`tool.py` 里换 `ddgs`，注意**必须自己 try/except**（ToolNode 默认只兜 `ToolInvocationError`，网络超时会直接让整张图崩）。

3. **`search` 节点是空转的**，只把 `topic` 原样返回；`materials` 字段从头到尾没人消费。要么让它真去取一批初始资料，要么把它和 `materials` 一起删掉。

4. **`assistant/agent.py` 是空文件**（0 字节），可以删。

5. **`finalize` 没有显式连到 `END`**。现在靠"节点没有出边就自动终止"生效，能跑，但语义隐式——建议补 `builder.add_edge("finalize", END)`。

6. **`MAX_COUNT = 8`** 偏高。意味着最多要人工审 8 轮，实际用起来很累，建议 3。

7. **`InMemorySaver` 不持久化**。脚本退出后中断记录就没了，"今天中断、明天接着审"做不到。需要落盘的话换 `SqliteSaver`。

---

## 参考资料

- `assistant/DESIGN.md` —— 综合项目的设计文档，含更详细的节点契约、interrupt 数据形状、启动顺序
