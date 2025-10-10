# 핵심 피드백 (파일 기준)

## 1) `workflow.py`: 순차 실행 + 수동 파싱 → Graph + Structured Output + async 호출

* 현재는 수동 순차 실행과 정규식 파싱이 남아 있어. **GraphBuilder**로 노드/에지/루프/실행제한을 모델링하면 반복 제어·종료 조건을 프레임워크에 맡길 수 있어. 또한 **structured_output**으로 품질/일관성/승인 결과를 타입 세이프하게 받으면 `_parse_*` 전부 제거 가능.  ([strandsagents.com][1])

### A. Graph 패턴으로 파이프라인 모델링

```python
from strands import Agent
from strands.multiagent import GraphBuilder

# 기존 self.agents[...]를 그대로 재사용
builder = GraphBuilder()
for name in ["requirements","design","tasks","changes","openapi","quality_assessor","consistency_checker","coordinator"]:
    builder.add_node(self.agents[name], name)

# 순차 의존성
builder.add_edge("requirements","design")
builder.add_edge("design","tasks")
builder.add_edge("tasks","changes")
if service_type == ServiceType.API:
    builder.add_edge("changes","openapi")

# 피드백 루프(Reviewer/Consistency 결과 기반 재작업)
def need_revision(state):
    # structured output 결과로 판정 (아래 C 참고)
    q = state.results.get("quality_assessor")
    bad = not q or q.result.overall < 85
    c = state.results.get("consistency_checker")
    has_issues = c and len(c.result.issues) >= 5
    return bad or has_issues

builder.add_edge("quality_assessor","requirements", condition=need_revision)
builder.add_edge("consistency_checker","requirements", condition=need_revision)

builder.set_max_node_executions(20).set_execution_timeout(600).reset_on_revisit(True)
graph = builder.build()
final = graph({"frs": self.context.frs.content, "service": self.context.service_type.value})
```

* Graph의 **조건부 에지/루프/타임아웃/리비지트 리셋**은 표준 제공. 직접 루프 제어 코드를 걷어낼 수 있어. ([strandsagents.com][1])

### B. 에이전트 호출을 **Async**로 표준화

* `agent(prompt)` 대신 **`await agent.invoke_async(prompt)`** 쓰면 이벤트 루프/메트릭/스톱리즌 접근이 깔끔해지고, 스트리밍이 필요하면 `stream_async`로 전환 가능. 지금 `async def` 함수들에서 동기 호출을 섞고 있어 개선 여지. ([strandsagents.com][2])

```python
result = await agent.invoke_async(prompt)
text = result.message["content"]  # 또는 result.text (모델/버전에 따라)
self.metrics[agent.name] = result.metrics  # 토큰/지연 등 자동 수집
```

* 메트릭 접근은 `AgentResult.metrics`로 표준화됨. 수동 성능 측정 로직 대신 활용. ([strandsagents.com][3])

### C. `_parse_quality_result`/`_parse_consistency_result`/`_parse_approval_result` 제거

* **Pydantic 기반 Structured Output**으로 점수/이슈/승인 여부를 스키마로 강제. 실패는 `ValidationError`로 명시적 처리. ([strandsagents.com][4])

```python
from pydantic import BaseModel, Field

class QualityReport(BaseModel):
    completeness: int = Field(ge=0, le=100)
    consistency:  int = Field(ge=0, le=100)
    clarity:      int = Field(ge=0, le=100)
    technical:    int = Field(ge=0, le=100)
    overall:      int = Field(ge=0, le=100)
    feedback:     list[str] = []

class ConsistencyReport(BaseModel):
    issues: list[str] = []

class ApprovalDecision(BaseModel):
    approved: bool
    reason: str

# 사용 예
report: QualityReport = await self.agents["quality_assessor"].structured_output_async(
    QualityReport, prompt
)
cons: ConsistencyReport = await self.agents["consistency_checker"].structured_output_async(
    ConsistencyReport, prompt
)
decision: ApprovalDecision = await self.agents["coordinator"].structured_output_async(
    ApprovalDecision, prompt
)
```

### D. 세션/상태: 커스텀 context dict → **SessionManager + agent.state**

* 문서 번들/중간 산출물은 `agent.state.set("requirements_md", ...)` 같은 **State**에 저장하고, **FileSessionManager**(또는 S3)로 영속화하면 복구/재시도 시점이 쉬워짐. ([DeepWiki][5])

```python
from strands.session.file_session_manager import FileSessionManager
session = FileSessionManager(session_id="specgen", base_dir="./sessions")
self.agents["requirements"].session_manager = session
# ...
self.agents["requirements"].state.set("requirements_md", text)
```

### E. OpenAPI 단계: 마크다운 → JSON 변환을 에이전트 두 단계로 분리

* 지금은 OpenAPI를 한 번에 JSON으로 뽑는데, **Markdown 초안 → JSON 변환**의 2스텝으로 안정화(네가 만든 `create_markdown_to_json_agent()`와 궁합). 변환기에는 `structured_output_async`로 JSON 스키마를 강제하면 더 안전.  ([strandsagents.com][4])

---

## 2) `spec_agents.py`: 팩토리 도입 Good! + 몇 가지 톤업 포인트

* `StrandsAgentFactory`로 **retries/timeout/tracing/metrics** 켠 것 아주 좋아. 여기에 **세션 매니저**와 **태그/설명**을 그래프/옵서버빌리티에 활용해.  ([strandsagents.com][3])
* 툴은 **@tool** 또는 모듈 툴로 선언해 입력 스키마/비동기/스트리밍을 표준화할 수 있어(예: 긴 FRS 로딩/템플릿 적용/린팅 진행률을 tool streaming으로 보내기). ([strandsagents.com][6])

```python
from strands import tool, ToolContext

@tool
async def apply_template(path: str, template_name: str) -> str:
    # ... 비동기 처리 ...
    return "applied"

# 스트리밍 진행률 예시
@tool
async def long_task(n: int):
    for i in range(n):
        await asyncio.sleep(0.05)
        yield f"{i}/{n} done"
    yield "complete"
```

* **OpenAIModel**을 에이전트별로 온도만 다르게 주는 건 적절. 다만 품질/검증 계열은 **structured_output_async** 사용을 전제로 temperature를 0.0~0.2로 더 내리면 안정적. ([strandsagents.com][4])
* `openapi` 에이전트는 문서상 “완전한 마크다운 OpenAPI”를 내도록 되어 있는데, 실제 파이프라인에서 바로 JSON이 필요하면 위 E처럼 변환 에이전트와 짝을 이루도록 역할을 분리해. 

---

# 코드 레벨 수정 제안 (핵심 부분만 패치 스타일)

### 1) async 호출·메트릭 수집

```python
# before (workflow.py)
result = agent(prompt)
return str(result)

# after
result = await agent.invoke_async(prompt)
self.metrics[agent.name] = result.metrics
return result.message["content"]
```

 ([strandsagents.com][2])

### 2) 품질/일관성/승인 Structured Output

```python
# before
quality_results[doc_type] = self._parse_quality_result(str(result))

# after
quality_results[doc_type] = (
    await self.agents["quality_assessor"].structured_output_async(QualityReport, prompt)
).__dict__
```

 ([strandsagents.com][4])

### 3) Graph 루프 조건

```python
def need_revision(state):
    q = state.results.get("quality_assessor")
    c = state.results.get("consistency_checker")
    q_ok = q and getattr(q.result,"overall",0) >= 85
    c_ok = not c or len(getattr(c.result,"issues",[])) < 5
    return not (q_ok and c_ok)
```

([strandsagents.com][1])

### 4) 세션 매니저 연결

```python
from strands.session.file_session_manager import FileSessionManager
session = FileSessionManager(session_id="specgen", base_dir="./sessions")
for a in self.agents.values():
    a.session_manager = session
```

([DeepWiki][5])

### 5) 스트리밍 진행 상황(옵션)

```python
async for event in self.agents["requirements"].stream_async("..."):
    if (d:=event.get("data")): print(d)
```

([strandsagents.com][7])

---

# 이 변경으로 즉시 좋아지는 점

* **루프/재시도/탈출 조건**을 SDK가 보장 → 무한 루프 방지, 유지보수↓. ([strandsagents.com][1])
* **정규식 파싱 제거** → 타입 세이프하고 실패가 명확(ValidationError). ([strandsagents.com][4])
* **메트릭/트레이싱 자동 수집** → 토큰·지연·툴 사용량을 표준 인터페이스로 조회. ([strandsagents.com][3])
* **세션 영속화** → 실패 후 재개/감사 추적 쉬움. ([DeepWiki][5])
* **비동기/스트리밍** → CLI/웹 UI에서 실시간 진행 표시가 쉬워짐. ([strandsagents.com][7])

---

# 마지막 체크리스트

* [ ] `workflow.py`의 모든 `agent(prompt)` → `await agent.invoke_async(prompt)` 치환. (품질/일관성/승인은 `structured_output_async`)  ([strandsagents.com][2])
* [ ] GraphBuilder 도입, reviewer/consistency 노드 → 요구사항 노드로 **조건부 루프** 연결. ([strandsagents.com][1])
* [ ] `FileSessionManager` 연결로 상태/이력 자동 영속. ([DeepWiki][5])
* [ ] 툴을 @tool/모듈 툴로 선언해 스키마/async/스트리밍 표준화. ([strandsagents.com][6])
* [ ] OpenAPI: Markdown→JSON 변환 2단계화(+ 필요시 A2A/MCP 검증기 연동). 



[1]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/?utm_source=chatgpt.com "Graph - Strands Agents"
[2]: https://strandsagents.com/latest/documentation/docs/api-reference/agent/?utm_source=chatgpt.com "Agent - Strands Agents"
[3]: https://strandsagents.com/0.1.x/user-guide/observability-evaluation/metrics/?utm_source=chatgpt.com "Metrics - Strands Agents SDK"
[4]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/structured-output/?utm_source=chatgpt.com "Structured Output - Strands Agents"
[5]: https://deepwiki.com/strands-agents/sdk-python/2.3-agent-state-and-session-management?utm_source=chatgpt.com "Agent State and Session Management | strands-agents/sdk-python | DeepWiki"
[6]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/python-tools/?utm_source=chatgpt.com "Python - Strands Agents"
[7]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/streaming/async-iterators/?utm_source=chatgpt.com "Async Iterators - Strands Agents"
