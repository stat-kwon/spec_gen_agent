````markdown
# Feature Specification: User Management Service

**Feature Branch**: `[123-user-management-service]`  
**Created**: 2024-01-15  
**Status**: Draft  
**Input**: User description: "모든 테넌트를 위한 통합 사용자 온보딩 및 인증 기능을 활성화합니다."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Self-service onboarding (Priority: P1)
사용자가 초대 링크 또는 공개 등록 폼을 통해 10분 이내에 계정을 생성할 수 있어야 합니다.

**Why this priority**: 사용자 온보딩의 효율성을 높이고, 지원 티켓 발행을 최소화하기 위해서입니다.

**Independent Test**: 사용자가 초대 링크를 통해 계정을 생성하는 과정을 독립적으로 검증할 수 있습니다.

**Acceptance Scenarios**:
1. **Given** 사용자가 초대 링크를 클릭하고, **When** 이메일 검증 및 비밀번호 설정을 완료하면, **Then** 계정이 생성되고 환영 메일이 발송된다.

---

### User Story 2 - MFA-protected sign-in (Priority: P1)
관리자와 재무 담당자는 사용자명/비밀번호와 OTP를 사용하여 로그인할 수 있어야 합니다.

**Why this priority**: 보안 강화를 위해 MFA를 필수로 적용해야 합니다.

**Independent Test**: MFA 로그인 과정에서 OTP 입력 및 계정 잠금 기능을 독립적으로 검증할 수 있습니다.

**Acceptance Scenarios**:
1. **Given** 사용자가 사용자명과 비밀번호를 입력하고, **When** OTP를 입력하면, **Then** 로그인 성공 시 JWT와 세션 감사 로그가 생성된다.

---

### User Story 3 - Profile self-management (Priority: P2)
기존 사용자가 프로필 정보를 수정하거나 계정 삭제를 요청할 수 있어야 합니다.

**Why this priority**: 사용자 경험을 개선하고 GDPR 준수를 위해 필요합니다.

**Independent Test**: 프로필 수정 및 삭제 요청 과정을 독립적으로 검증할 수 있습니다.

**Acceptance Scenarios**:
1. **Given** 사용자가 프로필 수정 요청을 하고, **When** 변경 사항을 저장하면, **Then** 감사 로그가 기록되고 변경 사항이 즉시 반영된다.

### Edge Cases
- 이미 사용된 초대 링크는 다시 사용할 수 없으며 재발송 안내를 제공해야 합니다.
- 비밀번호 재설정을 15분 내 5회 이상 시도하면 추가 요청이 제한됩니다.
- 다중 테넌트 환경에서 동일 이메일 사용 시 충돌이 발생하지 않아야 합니다.
- 외부 OAuth 인증 실패 시에도 로컬 자격 증명으로 안전하게 fallback 해야 합니다.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: 초대/직접 등록을 모두 지원하며, 등록 완료까지 10분 내 완료되도록 UX와 시간 제한을 제공한다.
- **FR-002**: RS256 서명된 JWT와 24시간 리프레시 토큰을 발급하고, 자격 증명 변경 시 즉시 무효화한다.
- **FR-003**: MFA(이메일 OTP, 인증 앱)를 제공하고 Privileged 역할에는 필수로 강제한다.
- **FR-004**: 프로필 수정, 비밀번호 변경, 계정 삭제 요청을 감사 이벤트와 GDPR 워크플로와 연결한다.
- **FR-005**: 역할·권한 변경은 승인 워크플로를 통해 2분 이내 모든 테넌트 서비스로 전파한다.

### Key Entities *(include if feature involves data)*
- **User**: 사용자 계정 정보, 권한, 프로필 데이터.

## Success Criteria *(mandatory)*

### Measurable Outcomes
- **SC-001**: 초대된 사용자 중 95% 이상이 첫 시도에서 등록을 완료하고 지원 티켓을 발행하지 않는다.
- **SC-002**: 관리자 로그인 실패 대비 계정 잠금 비율이 0.5% 미만이며, 잠금 해제까지 5분 이내 처리된다.
- **SC-003**: 감사 로그 적재 성공률 99.99% 이상, 실패 시 1분 내 재시도한다.
- **SC-004**: GDPR 삭제 요청의 98% 이상이 제출 후 24시간 내 소프트 삭제 및 파기 절차를 완료한다.
````
