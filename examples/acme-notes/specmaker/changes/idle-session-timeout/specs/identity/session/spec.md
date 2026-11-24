# identity/session

## MODIFIED Requirements

### Requirement: [SESS-02] Session validity
The system SHALL accept a session token only until the user signs out or the session has been idle for 30 minutes, and every accepted request SHALL restart the idle period.

#### Scenario: [SESS-02.1] Active session continues
- **GIVEN** a user whose last request was 29 minutes ago
- **WHEN** they make a request with their token
- **THEN** the request is accepted as that user
- **AND** the idle period starts again from this request

#### Scenario: [SESS-02.2] Sign-out invalidates the token
- **GIVEN** a user who signed out
- **WHEN** a request arrives with their old token
- **THEN** it is rejected with 401 and reason `session_invalid`

#### Scenario: [SESS-02.3] Idle session expires
- **GIVEN** a user whose last request was 30 minutes ago or more
- **WHEN** a request arrives with their token
- **THEN** it is rejected with 401 and reason `session_expired`
- **AND** the token is rejected with `session_invalid` from then on

## ADDED Requirements

### Requirement: [SESS-03] Absolute session lifetime
The system SHALL end every session 12 hours after sign-in, even if it was used continuously.

#### Scenario: [SESS-03.1] Long-running active session ends
- **GIVEN** a user who signed in 12 hours ago and has made a request every few minutes since
- **WHEN** they make another request
- **THEN** it is rejected with 401 and reason `session_lifetime_exceeded`
