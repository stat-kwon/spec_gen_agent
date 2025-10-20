# Feature Specification: User Management Service

**Feature Branch**: `[123-user-management-service]`  
**Created**: 2024-01-15  
**Status**: Draft  
**Input**: Product brief "Enable unified user onboarding and authentication for all tenants."

## Vision & Problem Statement
- 사내 여러 제품이 각자 사용자 온보딩과 인증을 구현하면서 보안 정책과 사용자 경험이 일관되지 않고 유지 비용이 증가하고 있습니다.  
- GDPR, SOC 2 등 규제가 강화되면서 사용자 데이터 보관·삭제·감사 요구를 중앙에서 통제할 수 있는 통합 서비스가 필요합니다.  
- 목표는 모든 테넌트가 동일한 API와 UX 흐름으로 등록·인증·프로필 관리를 처리하고, 보안·운영 팀이 정책을 한 곳에서 관리하도록 만드는 것입니다.

## Personas
- **Internal Admin (Operations Manager)**: 테넌트별 계정을 프로비저닝하고 기본 권한을 설정해야 하며, 지원 티켓 없이 초대/비활성화를 빠르게 수행하고 싶습니다.  
- **End User (Customer Employee)**: 초대 링크나 공개 등록 폼을 통해 서비스에 가입하고, 스스로 프로필을 갱신하거나 비밀번호를 초기화해야 합니다.  
- **Security Analyst**: MFA 적용 현황, 감사 로그, 계정 삭제 요청을 모니터링하고 규제 감사 시 근거 자료를 즉시 확보해야 합니다.

## Scope
### In Scope
- 초대 기반 및 직접 등록 흐름, 이메일 검증, 비밀번호 복잡도 정책  
- JWT 기반 인증/인가, 선택적 MFA, 계정 잠금 정책  
- 사용자 프로필 조회·수정, GDPR 준수를 위한 삭제 요청 워크플로  
- RBAC 역할/권한 관리, 웹훅 기반 권한 변경 전파  
- 감사 이벤트 스트림, 운영 및 보안 대시보드 연동을 위한 메트릭 수집

### Out of Scope
- SSO 연동(Okta, Azure AD 등) – 후속 단계에서 검토  
- 결제/청구 시스템과의 직접 통합  
- 모바일 전용 UI 또는 브랜드 커스터마이징  
- 비정상 활동에 대한 머신러닝 기반 탐지

## Assumptions & Open Questions
### Assumptions
- 각 테넌트는 기본 도메인과 이메일 발송 설정을 보유하고 있으며 SMTP 자격 증명을 제공한다.  
- 기존 PostgreSQL 클러스터가 있으며, 새로운 스키마 추가와 리드 레플리카 구성이 허용된다.  
- 운영 팀은 주 1회 이상 감사 로그를 검토하는 프로세스를 갖추고 있다.

### Open Questions
- OAuth 소셜 로그인(Google, GitHub 등)의 1차 지원 범위를 어떻게 정의할 것인가?  
- 다중 테넌트에서 이메일 도메인이 충돌할 경우 우선순위/정책은 어떻게 정할 것인가?  
- 지원 팀이 계정 삭제 요청을 취소하거나 보류할 수 있는 예외 절차가 필요한가?

## User Scenarios & Testing *(summary)*

### Scenario 1 - Self-service onboarding (Priority: P1)
초대 링크 또는 공개 등록 폼을 통해 사용자가 10분 이내에 계정을 생성한다.
- 등록 단계에서 이메일 검증, 비밀번호 정책, 기본 권한 부여를 모두 완료해야 한다.  
- 온보딩 완료 후 감사 이벤트(`UserRegistered`)를 발행하고 환영 메일을 보낸다.

### Scenario 2 - MFA-protected sign-in (Priority: P1)
관리자와 재무 담당자는 사용자명/비밀번호와 OTP를 사용하여 로그인한다.
- OTP 실패가 3회 이상이면 계정이 잠기고 보안 알림이 발송된다.  
- 성공 시 새 JWT·리프레시 토큰, 세션 감사 로그(`AdminLoginSucceeded`)를 생성한다.

### Scenario 3 - Profile self-management (Priority: P2)
기존 사용자가 프로필 정보를 수정하거나 계정 삭제를 요청한다.
- 변경 사항은 즉시 저장되고 감사 로그(`ProfileUpdated`)로 추적한다.  
- 삭제 요청은 24시간 내 소프트 삭제 후 GDPR 파기 절차를 자동 실행한다.

### Edge Cases
- 이미 사용된 초대 링크는 다시 사용할 수 없으며 재발송 안내를 제공해야 한다.  
- 비밀번호 재설정을 15분 내 5회 이상 시도하면 추가 요청이 제한된다.  
- 다중 테넌트 환경에서 동일 이메일 사용 시 충돌이 발생하지 않아야 한다.  
- 외부 OAuth 인증 실패 시에도 로컬 자격 증명으로 안전하게 fallback 해야 한다.

## Functional Overview *(summary)*
- **FR-001**: 초대/직접 등록을 모두 지원하며, 등록 완료까지 10분 내 완료되도록 UX와 시간 제한을 제공한다.  
- **FR-002**: RS256 서명된 JWT와 24시간 리프레시 토큰을 발급하고, 자격 증명 변경 시 즉시 무효화한다.  
- **FR-003**: MFA(이메일 OTP, 인증 앱)를 제공하고 Privileged 역할에는 필수로 강제한다.  
- **FR-004**: 프로필 수정, 비밀번호 변경, 계정 삭제 요청을 감사 이벤트와 GDPR 워크플로와 연결한다.  
- **FR-005**: 역할·권한 변경은 승인 워크플로를 통해 2분 이내 모든 테넌트 서비스로 전파한다.

## Success Criteria *(summary)*
- **SC-001**: 초대된 사용자 중 95% 이상이 첫 시도에서 등록을 완료하고 지원 티켓을 발행하지 않는다.  
- **SC-002**: 관리자 로그인 실패 대비 계정 잠금 비율이 0.5% 미만이며, 잠금 해제까지 5분 이내 처리된다.  
- **SC-003**: 감사 로그 적재 성공률 99.99% 이상, 실패 시 1분 내 재시도한다.  
- **SC-004**: GDPR 삭제 요청의 98% 이상이 제출 후 24시간 내 소프트 삭제 및 파기 절차를 완료한다.
