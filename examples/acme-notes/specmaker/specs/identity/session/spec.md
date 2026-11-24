# identity/session

## Purpose

Lets a signed-in team member keep working without re-entering credentials on every request, and ends that access when it should end.

## Requirements

### Requirement: [SESS-01] Session creation
The system SHALL issue a new, unguessable session token when a user signs in successfully.

#### Scenario: [SESS-01.1] Sign-in returns a token
- **WHEN** a user signs in with valid credentials
- **THEN** the response carries a new session token
- **AND** requests with that token are accepted as that user

### Requirement: [SESS-02] Session validity
The system SHALL accept a session token until the user signs out.

#### Scenario: [SESS-02.1] Token works until sign-out
- **GIVEN** a user who signed in
- **WHEN** they make a request with their token
- **THEN** the request is accepted as that user

#### Scenario: [SESS-02.2] Sign-out invalidates the token
- **GIVEN** a user who signed out
- **WHEN** a request arrives with their old token
- **THEN** it is rejected with 401 and reason `session_invalid`
