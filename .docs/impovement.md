# 1) 오케스트레이션: 커스텀 루프 → Strands **Graph/Workflow** 패턴

### 왜:

Strands는 멀티에이전트 오케스트레이션을 위해 **Graph/Workflow/Swarm** 3가지 패턴을 제공해. 너처럼 “요구사항 → 설계 → 태스크 → 변경사항 → (API면) OpenAPI → 평가/개선”처럼 **결정적 순서 + 피드백 루프**가 있는 파이프라인엔 **Graph**(조건부 에지 + 루프 + 실행제한) 또는 **Workflow**가 딱 맞아. ([strandsagents.com][1])

### 어떻게: GraphBuilder로 명세 체인을 구성하고, 품질 검토 노드를 **루프 에지**로 연결

```python
from strands import Agent
from strands.multiagent import GraphBuilder

# 개별 에이전트
requirements = Agent(name="requirements", system_prompt="FRS로 요구사항 md를 작성하라.")
design       = Agent(name="design",       system_prompt="요구사항으로 설계 md를 작성하라.")
tasks        = Agent(name="tasks",        system_prompt="설계로 구현 태스크 md를 작성하라.")
changes      = Agent(name="changes",      system_prompt="변경내역 md를 작성하라.")
openapi      = Agent(name="openapi",      system_prompt="핵심 5개 엔드포인트의 OpenAPI를 작성하라.")
reviewer     = Agent(name="reviewer",     system_prompt="각 산출물을 채점하고 개선 피드백을 구조화하라.")

# 그래프 구성
g = GraphBuilder()
g.add_node(requirements, "requirements")
g.add_node(design, "design")
g.add_node(tasks, "tasks")
g.add_node(changes, "changes")
g.add_node(openapi, "openapi")
g.add_node(reviewer, "reviewer")

# 순차 의존성
g.add_edge("requirements", "design")
g.add_edge("design", "tasks")
g.add_edge("tasks", "changes")
g.add_edge("changes", "openapi")

# 피드백 루프(리뷰어 결과가 임계 미달이면 요구사항으로 되돌림)
def need_improve(state):
    return (state["reviewer"].get("overall", 0) < 80)

g.add_edge("reviewer", "requirements", condition=need_improve)
g.set_entry_point("requirements")\
 .set_max_node_executions(20)\
 .reset_on_revisit(True)

graph = g.build()
result = graph("FRS 경로 혹은 입력 텍스트")
```

* **조건부 에지**, **루프**, **실행 제한**, **리비지트 시 상태 초기화** 같은 제어는 SDK가 제공. 직접 반복 제어 로직을 덜어낼 수 있어. ([strandsagents.com][1])

> 팁: 네가 구상한 *Workflow* 용어도 문서에 있지만, 코드 예제와 제어 옵션(loops/conditions)은 Graph 쪽이 훨씬 풍부해. 명세 생성 파이프라인엔 Graph를 기본으로 추천. ([strandsagents.com][2])

---

# 2) 에이전트 간 통신: 커스텀 메시징 → **A2A** 표준

### 왜:

Strands는 **Agent-to-Agent(A2A)** 표준을 지원해. 내부/외부 에이전트를 프로토콜로 붙이고, 원격 검증기(예: OpenAPI Linter)도 쉽게 연결 가능. 수동 통신 코드를 걷어낼 수 있어. ([strandsagents.com][3])

### 어떻게: 원격 검증 에이전트를 A2A 서버로, 로컬에서 **A2A client tools**를 에이전트에 장착

```python
from strands.multiagent.a2a import A2AServer
from strands_tools.calculator import calculator
from strands import Agent

# (원격) 검증 에이전트 예시
validator_agent = Agent(name="openapi_validator", tools=[calculator])  # 실제론 OpenAPI 검증 툴 바인딩
A2AServer(agent=validator_agent, port=9000).serve()

# (로컬) 클라이언트 툴 프로바이더로 원격 에이전트 발견/호출
from strands.multiagent.a2a import A2AClientToolProvider
provider = A2AClientToolProvider(known_agent_urls=["http://localhost:9000"])
agent = Agent(tools=provider.tools)
```

A2A는 **동기/스트리밍 클라이언트**, **에이전트를 툴처럼 사용**하는 패턴을 모두 제공. ([strandsagents.com][3])

---

# 3) 상태/세션/번들: 커스텀 번들 클래스 → Strands **State & SessionManager**

### 왜:

Strands는 **대화 히스토리**, **에이전트 상태(key-value)**, **요청 상태**를 분리 관리하고, **FileSessionManager/S3 등**으로 자동 영속화를 제공. 직접 번들/복구 코드를 거의 제거 가능. ([strandsagents.com][4])

### 어떻게:

```python
from strands import Agent
from strands.session.file_session_manager import FileSessionManager

session = FileSessionManager(session_id="specgen", base_dir="./sessions")
agent = Agent(id="requirements", session_manager=session)

# 산출물은 대화가 아닌 상태로 저장
agent.state.set("requirements_md", "# 요구사항 ...")
# 요청 스코프 임시 값은 request_state로 (hooks/stream에서 접근)
```

* 세션은 **훅 이벤트**와 연동되어 메시지 추가/종료 시 자동 동기화됨. ([DeepWiki][5])

---

# 4) 평가/품질: 수동 파싱 → **Structured Output + Hooks + Metrics**

### 왜:

점수/이슈를 텍스트에서 정규식 파싱하던 부분을 **Pydantic 기반 Structured Output**으로 바꾸면 **타입 보장/검증/예외 처리**가 자동화돼. 여기에 **Hooks/Callback**으로 실행 전후 이벤트를 잡고, **Metrics**로 토큰/지연/툴 사용량을 자동 수집. ([strandsagents.com][6])

### 어떻게:

```python
from pydantic import BaseModel, Field
from strands import Agent

class QualityReport(BaseModel):
    completeness: int = Field(ge=0, le=100)
    consistency:  int = Field(ge=0, le=100)
    clarity:      int = Field(ge=0, le=100)
    technical:    int = Field(ge=0, le=100)
    overall:      int = Field(ge=0, le=100)
    issues: list[str] = []

reviewer = Agent(system_prompt="산출물을 채점하고 JSON으로만 반환해라.")
report: QualityReport = reviewer.structured_output(QualityReport, "채점 대상 텍스트...")
print(report.overall)  # 수동 파싱 불필요
```

* **Hooks**로 Before/AfterInvocation, Before/AfterToolCall 등 이벤트에 로깅/임계값 조정/얼리스톱 신호를 넣을 수 있음. ([strandsagents.com][7])
* **AgentResult.metrics**로 토큰/루프 횟수/지연을 자동 집계. 자체 QualityScore 시스템은 **메트릭 태깅**으로만 남기고 계산은 모델이 하게끔 단순화. ([strandsagents.com][8])

---

# 5) 툴 생태계: 파일/Git/검증/그래프 → **strands-agents-tools** & MCP

### 왜:

파일 입출력, 셸 실행, 그래프 조립 툴 등은 커스텀 구현보다 커뮤니티 툴을 쓰는 게 안전·표준. OpenAPI 검증은 **MCP** 또는 A2A로 외부 밸리데이터(예: IBM openapi-validator)와 연결. ([GitHub][9])

### 어떻게:

```python
from strands import Agent
from strands_tools import file_read, file_write, shell  # 커뮤니티 툴
agent = Agent(tools=[file_read, file_write, shell])
```

* OpenAPI 검증기는 **MCP 서버**(또는 A2A 서버)로 감싸고, 에이전트가 원격 툴을 호출해 린트/스키마 체크를 수행. ([strandsagents.com][10])

---

# 6) 스트리밍/비동기/에러 처리: 수동 출력/재시도 → **stream_async + 내장 리커버리**

* **stream_async**로 진행 상황을 실시간 스트리밍(**기본 프린팅 핸들러** 제공) → 수동 프로그레스 출력 제거. ([strandsagents.com][11])
* **컨텍스트 초과 시 자동 축소/재시도**, 툴 실행시 표준 에러 결과를 반환하는 **툴 실행기 예외 처리**가 내장되어 있음(툴 미발견/예외/이름 검증 등). ([DeepWiki][12])

---

# 7) 네가 적어준 Phase별 계획 ↔ 문서 기반 실행 체크리스트

## Phase 1 — 멀티 에이전트 아키텍처 재설계

* [ ] **Graph 패턴**으로 파이프라인 모델링(조건부 에지/루프/실행 제한/노드 타임아웃). ([strandsagents.com][1])
* [ ] 리뷰어(품질/정합) 노드를 추가하고 **루프 조건**으로 연결. **loops 예제**를 참고. ([strandsagents.com][13])
* [ ] 원격 검증/요약기를 **A2A**로 분리해 재사용/스케일 아웃. ([strandsagents.com][3])

## Phase 2 — 상태 관리/관찰성

* [ ] `FileSessionManager` 또는 저장소 기반 세션으로 **자동 영속화**. ([Amazon Web Services, Inc.][14])
* [ ] 커스텀 번들 삭제 → **agent.state** / **session**로 대체. ([strandsagents.com][4])
* [ ] **Hooks + Metrics**로 품질·리소스 지표 수집, 대시보드 연동(OTel). ([strandsagents.com][7])

## Phase 3 — 커뮤니티 도구 & 고급 기능

* [ ] `strands-agents-tools` 파일/그래프/웹/셸 툴 채택. ([GitHub][9])
* [ ] **MCP**로 외부 밸리데이터/리소스를 일관되게 연결. ([strandsagents.com][15])

## Phase 4 — 최적화/운영

* [ ] **stream_async**로 UI/CLI 스트리밍 일원화. ([strandsagents.com][11])
* [ ] 그래프의 **타임아웃/실행 제한/리비지트 리셋**으로 안정성 강화. ([strandsagents.com][16])

---

# 8) “직접 구현 → Strands 기능” 매핑 요약

| 현재 직접 구현       | 권장 대체                                             | 핵심 근거                                           |
| -------------- | ------------------------------------------------- | ----------------------------------------------- |
| 커스텀 반복/개선 루프   | **Graph** 루프 + 조건부 에지 + `set_max_node_executions` | 루프/조건/제한 제공 ([strandsagents.com][1])            |
| 수동 품질 평가/파싱    | **Structured Output**(Pydantic)으로 타입 검증           | 파싱 제거/검증 내장 ([strandsagents.com][6])            |
| 커스텀 에이전트 통신    | **A2A** 서버/클라이언트/툴                                | 표준 프로토콜/디스커버리 ([strandsagents.com][3])          |
| 수동 상태/번들 관리    | **State & SessionManager**                        | 자동 영속/복구/분리된 state 레이어 ([strandsagents.com][4]) |
| 수동 에러/폴백       | **툴 실행기 표준 에러 처리** + **컨텍스트 축소/재시도** + **Hooks**  | 예외/재시도/정리 이벤트 표준화 ([DeepWiki][17])              |
| 수동 스트리밍/프로그레스  | **stream_async + 기본 콜백 핸들러**                      | 실시간 이벤트/간단 출력 ([strandsagents.com][11])         |
| 수동 파일/Git/검증 툴 | **strands-agents-tools + MCP/A2A 외부 밸리데이터**       | 커뮤니티 툴/표준 통합 ([GitHub][9])                      |

---

# 9) 마이그레이션 예시(핵심 두 부분만)

## (A) reviewer의 점수 산출 → Structured Output

```python
class Review(BaseModel):
    overall: int
    reasons: list[str] = []

reviewer = Agent(system_prompt="산출물 평가를 JSON으로만 반환하라.")
review: Review = reviewer.structured_output(Review, prompt="요구/설계/태스크/변경안을 평가해라.")
```

→ 기존 정규식 파서를 전부 제거 가능. 실패 시 `ValidationError`로 명확히 핸들. ([strandsagents.com][6])

## (B) OpenAPI 검증 → MCP/A2A 원격 툴 호출

```python
# 예: MCP로 openapi-validator(노드 패키지)를 감싼 서버에 연결
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client

with MCPClient(lambda: streamablehttp_client("http://localhost:8001/mcp/")) as mcp:
    tools = mcp.list_tools_sync()  # "openapi_validate" 같은 도구 노출
    validator_agent = Agent(tools=tools)
    res = validator_agent("apis.json을 검증하고 주요 오류만 요약해줘")
```

([strandsagents.com][10])

---

# 10) 리스크/주의

* **A2A가 실험적/버전 차이**가 있을 수 있으니 `latest` 문서/버전을 따르고 샘플 코드로 먼저 검증해. ([strandsagents.com][18])
* **세션/상태 저장소 선택**(파일 vs S3 등)은 운영 환경에 맞게. 파일은 로컬 개발에 적합. ([Amazon Web Services, Inc.][14])
* **그래프 루프 탈출 조건**은 구조화된 점수로 명확히(예: overall≥80 AND blocker=0). 그래프의 `set_max_node_executions`로 세이프가드 추가. ([strandsagents.com][1])


[1]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/graph/?utm_source=chatgpt.com "Graph - Strands Agents"
[2]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/workflow/?utm_source=chatgpt.com "Workflow - Strands Agents"
[3]: https://strandsagents.com/latest/user-guide/concepts/multi-agent/agent-to-agent/?utm_source=chatgpt.com "Agent2Agent (A2A) - Strands Agents SDK"
[4]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/state/?utm_source=chatgpt.com "State - Strands Agents"
[5]: https://deepwiki.com/strands-agents/sdk-python/2.3-agent-state-and-session-management?utm_source=chatgpt.com "Agent State and Session Management | strands-agents/sdk-python | DeepWiki"
[6]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/structured-output/?utm_source=chatgpt.com "Structured Output - Strands Agents"
[7]: https://strandsagents.com/latest/documentation/docs/api-reference/hooks/?utm_source=chatgpt.com "Hooks - Strands Agents"
[8]: https://strandsagents.com/latest/documentation/docs/user-guide/observability-evaluation/metrics/?utm_source=chatgpt.com "Metrics - Strands Agents"
[9]: https://github.com/wzxxing/strands-tools?utm_source=chatgpt.com "GitHub - wzxxing/strands-tools: A set of tools that gives agents powerful capabilities."
[10]: https://strandsagents.com/latest/documentation/docs/examples/python/mcp_calculator/?utm_source=chatgpt.com "MCP - Strands Agents"
[11]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/streaming/callback-handlers/?utm_source=chatgpt.com "Callback Handlers - Strands Agents"
[12]: https://deepwiki.com/strands-agents/sdk-python/2.2-conversation-management?utm_source=chatgpt.com "Conversation Management | strands-agents/sdk-python | DeepWiki"
[13]: https://strandsagents.com/latest/documentation/docs/examples/python/graph_loops_example/?utm_source=chatgpt.com "Cyclic Graph - Strands Agents"
[14]: https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/?utm_source=chatgpt.com "Introducing Strands Agents 1.0: Production-Ready Multi-Agent Orchestration Made Simple | AWS Open Source Blog"
[15]: https://strandsagents.com/latest/documentation/docs/user-guide/concepts/tools/mcp-tools/?utm_source=chatgpt.com "Model Context Protocol (MCP) - Strands Agents"
[16]: https://strandsagents.com/latest/documentation/docs/api-reference/multiagent/?utm_source=chatgpt.com "Multiagent - Strands Agents"
[17]: https://deepwiki.com/strands-agents/sdk-python/4.2-mcp-integration?utm_source=chatgpt.com "Tool Execution and Handling | strands-agents/sdk-python | DeepWiki"
[18]: https://strandsagents.com/0.1.x/documentation/docs/user-guide/concepts/multi-agent/agent-to-agent/?utm_source=chatgpt.com "Agent2Agent (A2A) - Strands Agents"
