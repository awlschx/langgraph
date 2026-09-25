# 资料整理助手 · 技术文档

写代码时对照这份文档，不用回去翻聊天记录。

---

## 0. 项目定位

**是**：一个把 LangGraph 课程知识点串起来的可运行骨架。

**不是**：一个真能用的资料整理工具。整理资料直接问大模型更快。

判断"做对了没有"的标准**不是**"功能好不好用"，而是：

> 每个知识点是否都有**非用不可**的位置——拿掉任何一块，流程都走不通。

| 概念 | 落在哪 | 拿掉会怎样 | 版本 |
|---|---|---|---|
| State / 多字段 | 全局状态 | 节点之间没法传数据 | v1 |
| `reducer` | `feedback` 累积意见 | 第二轮意见覆盖第一轮，看不到历史 | v1 |
| 节点 + 边 | 检索 / 起草 / 审核 / 定稿 | 流程不存在 | v1 |
| **条件边** | 审核后分「通过 / 驳回 / 超限」三路 | 无论审核结果都走同一条路，人工审核没意义 | v1 |
| **循环** | 驳回 → 回到起草 | 只有一次机会，驳回就死 | v1 |
| `interrupt` + `Command(resume)` | 审核那一步等人 | 变成全自动，没有"人工" | v1 |
| checkpointer + thread_id | 支撑中断、回看每轮 | interrupt 恢复时报错 | v1 |
| `@tool` + ToolNode | draft 升级成 agent 后，模型自己决定要不要再查资料 | 模型只能"一次成型"，没工具可选 | **v3** |

> 注意：`@tool` + ToolNode **不在 v1**，是 v3 才登场的。为什么，见第 7 节。

---

## 1. 目录结构

以下路径相对于仓库根目录（`lg_cource/myrepo/`）。

```
assistant/
  DESIGN.md      ← 本文档
  state.py       ← State 定义 + 常量（MAX_ROUNDS）
  nodes.py       ← 四个节点（v1 里 search/finalize 是普通函数）
  graph.py       ← 搭图 + 条件边
  main.py        ← 入口：跑流程、处理 interrupt 循环
  tools.py       ← v3 才出现：给 draft-agent 用的工具
```

分文件不是为了"看起来专业"，是改某个节点时不用在 300 行里翻找。

---

## 2. State 设计

### 2.1 字段

```python
class State(TypedDict):
    topic: str                                    # 输入
    materials: str                                # search 产出
    draft: str                                    # draft 产出
    feedback: Annotated[list[str], operator.add]  # 累积的驳回意见
    round: int                                    # 第几版草稿
    approved: bool                                # 审核结论
    doc_path: str                                 # 最终文件路径
```

| 字段 | 谁写 | 说明 |
|---|---|---|
| `topic` | 调用方 | `invoke()` 入参 |
| `materials` | `search` | 搜集到的资料（v1 是假数据） |
| `draft` | `draft` | 每轮重写都覆盖 |
| `feedback` | `review` | **追加**，不覆盖 |
| `round` | `draft` | **覆盖**，每写一版 +1 |
| `approved` | `review` | 覆盖 |
| `doc_path` | `finalize` | 覆盖 |

### 2.2 reducer 为什么只加在 `feedback` 上

- `feedback` 是**累积**语义：第三轮的驳回意见不该把第一轮的冲掉，否则看不到完整修改历史。所以用 `Annotated[list[str], operator.add]`。
- `round`、`draft`、`approved` 都是**覆盖**语义：只关心最新值。**不要**给它们加 reducer。

两者行为完全不同，别搞混：

```python
return {"round": 5}          # 覆盖，state["round"] 变成 5
return {"feedback": ["意见"]} # 追加，state["feedback"] 变成 [...旧, "意见"]
```

（`operator.add` 必须 `import operator`。裸写 `add` 会 `NameError`，除非你 `from operator import add`。）

### 2.3 初始值规则（实测结论）

| 字段类型 | 入口要传吗 | 不传会怎样 |
|---|---|---|
| 有 reducer（`feedback`） | **不用** | 自动初始化成 `[]`，正常 |
| 普通字段（`round`） | **必须传** | 节点里 `state["round"]` → `KeyError: 'round'` |

所以入口必须写成：

```python
graph.invoke({"topic": topic, "round": 0}, config)   # feedback 可以省
```

`round` 的语义定成**"第几版草稿"**，不是"第几轮审核"。后面判断循环上限时会清楚很多。

---

## 3. 节点契约

先写契约再写实现。每个节点只需要回答"读什么、返回什么"。

| 节点 | 读 | 返回 | 说明 |
|---|---|---|---|
| `search` | `topic` | `{"materials": str}` | v1 返回假数据 |
| `draft` | `topic`, `materials`, `feedback` | `{"draft": str, "round": int}` | `round` = 入参 round + 1 |
| `review` | `draft`, `round`, `feedback` | `interrupt()` 的结果决定 | 见第 5 节 |
| `finalize` | `draft` | `{"doc_path": str}` | 写文件 |

### `draft` 怎么用上意见（关键）

`state["feedback"]` 里**最后一条**就是上一轮的驳回理由。

```python
last = state["feedback"][-1] if state["feedback"] else None
```

把这个意见拼进你的模板（v3 之后拼进 prompt）。**不拼的话每轮生成的草稿都一样，循环永远不收敛**——这是整个循环能不能工作的命门。

### `round` 放在 `draft` 里自增

因为 `draft` 每写一版就跑一次，`round` 天然等于"第几版"。放在 `review` 里也能用，但语义会绕。

---

## 4. 图的连接

```
START → [search] → [draft] → [review]
                                │
                   条件边 ───────┼── approved=True ──→ [finalize] → END
                                │
                                ├── round >= MAX_ROUNDS → [finalize] → END
                                │
                                └── 其他 ──────────────→ 回到 [draft]
```

### 条件边必须写三路，不是两路

新手最常犯的错是只写"通过 / 不通过"，然后驳回就死循环。三路：

```python
def route_after_review(state: State) -> str:
    if state["approved"]:
        return "finalize"
    if state["round"] >= MAX_ROUNDS:
        return "finalize"      # ← 这一条最容易漏
    return "draft"
```

`MAX_ROUNDS` 建议设 3，放在 `state.py` 里作为模块常量。

---

## 5. interrupt 契约

### 往外送什么（payload）

```python
decision = interrupt({
    "draft": state["draft"],
    "round": state["round"],
    "history": state["feedback"],    # 之前所有驳回意见，方便人回顾
})
```

这个 dict 会原样出现在调用方的 `result["__interrupt__"][0].value` 里，你拿它生成"给人看的界面"（命令行就是 print）。

### 收回来什么（resume）

用 **dict**，不要用裸 bool——因为驳回时还得把意见带回来：

```python
{"approved": True}                                  # 通过
{"approved": False, "comment": "太长了，只留要点"}   # 驳回 + 意见
```

### `review` 节点怎么写

```python
def review(state: State):
    decision = interrupt({...})          # ← 放节点第一行，见第 8 节
    if decision["approved"]:
        return {"approved": True}
    return {"approved": False, "feedback": [decision["comment"]]}
```

注意：`feedback` 返回的是**只含一条意见的列表**——reducer 会把它追加进去，不要返回完整列表。

---

## 6. 入口循环（最容易写错的地方）

**人的直觉是"invoke 一次 → resume 一次 → 结束"。这是错的。**

> resume 之后，图可能**再次中断**。因为驳回会回到 draft，下一轮 draft 完又进 review，又触发一次 interrupt。

所以入口必须是**循环**：

```python
config = {"configurable": {"thread_id": "随便一个固定字符串"}}

result = graph.invoke({"topic": topic, "round": 0}, config)

while result.get("__interrupt__"):        # ← 关键：一直循环到不再中断
    payload = result["__interrupt__"][0].value
    # 把 payload 展示给人（草稿、第几版、历史意见）
    answer = input("通过？(y 或直接输入修改意见): ")
    if answer == "y":
        decision = {"approved": True}
    else:
        decision = {"approved": False, "comment": answer}
    result = graph.invoke(Command(resume=decision), config)   # 可能又中断

print(result["doc_path"])
```

想清楚这个 `while` 就通了——**中断是可能发生多次的，不是一次性的**。

---

## 7. 分阶段实现计划

三个版本，每版都能独立跑通。原则：**图和模型是两套独立的失败来源**，分开验证——同时上，报错时你分不清是图搭错了还是 API 出错了。

### v1：纯骨架（不接模型、不用工具）

| 环节 | 实现 |
|---|---|
| `search` | 返回硬编码的假数据（普通函数） |
| `draft` | 模板拼字符串 |
| `review` | interrupt + resume |
| `finalize` | 写文件（普通函数） |

**这一版没有 `@tool`、没有 ToolNode、没有模型调用。**

### v2：换掉 search

`search` 换成真实检索（联网 / 读本地文件）。仍是**普通函数**，不是 `@tool`——它还是固定动作，不需要模型决策。

### v3：draft 升级成 agent，ToolNode 在这里登场

把 `draft` 从"模板拼字符串"换成"带工具的模型"：

```
draft = agent(带工具)
   工具：search_more(关键词)   —— 模型觉得资料不够时，自己决定再查一次
   循环：查 → 看够不够 → 不够再查 → 够了输出草稿
```

**ToolNode 只有在 v3 才有非用不可的理由**：因为"模型自己决定要不要再查、查什么"这个决策，才需要 `bind_tools` + `ToolNode` + `tools_condition`。v1/v2 里硬塞工具，属于为了用而用——固定流程里没有"模型自己挑工具"这个动作，`@tool` 和 ToolNode 都没有存在意义。

---

## 8. 坑清单

1. **`review` 节点恢复时会从函数开头重跑**（恢复时 LangGraph 重新调用整个函数，这次 `interrupt()` 直接返回而不暂停）。
   所以 `interrupt()` **之前的代码不能有副作用**——别在它前面写文件、发请求、扣钱。
   **最稳的写法：`interrupt()` 放节点第一行。** 这条是硬要求。

2. **reducer 只对 `Annotated` 标注的字段生效**。见 2.2。

3. **`resume` 传的值 = `interrupt()` 的返回值**。这两个方向别搞反：
   - `interrupt({...})` 里的字典是**往外送**给人看的
   - `resume=xxx` 里的 xxx 是**往里传**回来给 `interrupt()` 当返回值的

4. **缺 checkpointer 只会在「恢复」时报错**，不在中断时报错。
   所以编译时忘了 `checkpointer=`，第一次 invoke 看起来一切正常，直到你 resume 才炸：

   ```
   RuntimeError: Cannot use Command(resume=...) without checkpointer
   ```

5. **同一个 thread_id 才能接上同一次中断**。换个 thread_id 就是全新的一条线，checkpointer 找不到那条中断记录。

---

## 9. 推进顺序（重要）

**不要一次写完四个节点再跑**，会一次面对一堆报错。按这个顺序，每步都能单独验证：

1. `search` + `draft` + `finalize`，先用**直线**连起来
   `START → search → draft → finalize → END`，能跑出文件
2. 插入 `review` 节点和 `interrupt`，验证：能停下、`__interrupt__` 里有东西、能 resume
3. 接上 `review → draft` 的回边 + 条件边，加 `MAX_ROUNDS`，验证：能驳回、能循环、能收敛
4. 最后把 `draft` 升级成带工具的 agent（引入 ToolNode），见第 7 节 v3

**前 3 步完全不需要模型**，也不需要联网。

---

## 10. 环境准备

### 依赖

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install langgraph langchain-openai python-dotenv
```

v1~v3 的前 3 步只需要 `langgraph`；`langchain-openai` 和 `python-dotenv` 是 v3 接模型才用得上。

### API key（v3 才需要）

项目根目录（`lg_cource/myrepo/`）需要一个 `.env` 文件，内容一行：

```
DEEPSEEK_API_KEY=sk-你的key
```

- `.env` 已经在 `.gitignore` 里，不会被提交。
- key 就是本机环境变量 `ANTHROPIC_AUTH_TOKEN` 里那个 DeepSeek key（`sk-` 开头）。
- 如果这个文件不存在了，用下面的方式重新生成，**不要把 key 写进代码**：

  ```bash
  printf 'DEEPSEEK_API_KEY=%s\n' "$ANTHROPIC_AUTH_TOKEN" > .env
  ```

v3 接模型时，脚本开头 `load_dotenv()` 会自动读它：

```python
from dotenv import load_dotenv
import os
load_dotenv()
model = ChatOpenAI(model="deepseek-chat",
                   base_url="https://api.deepseek.com/v1",
                   api_key=os.getenv("DEEPSEEK_API_KEY"),
                   temperature=0)
```

### 控制台编码

Windows 控制台是 GBK，脚本开头加这个，否则中文输出乱码：

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
```
