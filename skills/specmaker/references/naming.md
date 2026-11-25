# Naming Conventions

This is the standard naming convention for every specmaker change, in any
programming language. It applies to the names the propose phase fixes in the
LLD, contracts and file boundary, and to all code written in sprints.
Reviewers check against it.

**Precedence, highest first:**

1. The repository's own rules: `project.md` → Conventions, plus linters and
   formatters already configured.
2. The language's idioms (the casing table below).
3. This guide.

When they conflict, follow the higher one, and say so in the LLD if it is not
obvious. External contracts win over everything for the names they control: a
JSON API, a database schema or a protocol keeps its own spelling at the
boundary.

Examples use TypeScript first, then the equivalent in other popular languages
where they differ.

## Casing by language

| Language | Variables, functions | Types, classes | Constants | Files and modules | Private or internal |
|---|---|---|---|---|---|
| TypeScript, JavaScript | `camelCase` | `PascalCase` | `UPPER_SNAKE` (module-level, truly constant) or `camelCase` | `kebab-case.ts` (or the repo's rule) | `#field`, or no export |
| Python | `snake_case` | `PascalCase` | `UPPER_SNAKE` | `snake_case.py` | `_leading_underscore` |
| Go | `camelCase` (unexported), `PascalCase` (exported) | `PascalCase` / `camelCase` by export | `PascalCase` / `camelCase` (no `UPPER_SNAKE`) | `lowercase` packages, `snake_case.go` files | lowercase first letter |
| Java | `camelCase` | `PascalCase` | `UPPER_SNAKE` (`static final`) | `PascalCase.java`, `lower.dot.packages` | `private` modifier |
| Kotlin | `camelCase` | `PascalCase` | `UPPER_SNAKE` (`const val`) | `PascalCase.kt` | `private` / `internal` |
| C# | `camelCase` locals and params, `PascalCase` methods and properties | `PascalCase`, interfaces `IPascalCase` | `PascalCase` | `PascalCase.cs` | `_camelCase` fields |
| Rust | `snake_case` | `PascalCase` | `UPPER_SNAKE` | `snake_case.rs` | no `pub` |
| Swift | `camelCase` | `PascalCase` | `camelCase` | `PascalCase.swift` | `private` / `fileprivate` |
| C++ | follow the repo style guide (`snake_case` or `camelCase`) | `PascalCase` | `kPascalCase` or `UPPER_SNAKE` | `snake_case.cpp` / `.h` | trailing `_` members (`count_`) |
| Ruby | `snake_case` | `PascalCase` | `UPPER_SNAKE` | `snake_case.rb` | `private` section |
| PHP | `camelCase` | `PascalCase` | `UPPER_SNAKE` | `PascalCase.php` (PSR-4) | `private` |
| SQL | `snake_case` tables and columns | n/a | n/a | `NNNN_snake_case.sql` migrations | n/a |
| Env vars, CLI flags | `UPPER_SNAKE` env vars; `--kebab-case` flags | n/a | n/a | n/a | n/a |

**Acronyms.** Treat an acronym as a word in camel and Pascal case
(`userId`, `HttpClient`, `parseJson`). There are two exceptions:

- **Go** keeps acronyms in one case: `userID`, `HTTPClient`, `parseJSON`.
- **C#** writes two-letter acronyms in capitals (`IOStream`) and longer ones as
  words (`HttpClient`).

## 1. Use English for naming

All variables, functions, classes and other identifiers use English words, for
consistency and readability across the codebase. Domain terms in another
language are allowed only when they are proper nouns or regulated names (such
as a tax form ID). Record them in the LLD glossary.

```ts
/* Bad */
const primerNombre = 'Gustavo'
const amigos = ['Kate', 'John']

/* Good */
const firstName = 'Gustavo'
const friends = ['Kate', 'John']
```

```python
# Good
first_name = "Gustavo"
friends = ["Kate", "John"]
```

## 2. Use standard casing

Follow the casing table for the language. Use another casing only where an
external schema requires it, and only at that boundary.

```ts
/* Bad in TypeScript */
const page_count = 5

/* Good */
const pageCount = 5
const shouldUpdate = true

/* Good where an external schema requires snake_case */
const page_count = 5
const should_update = true
```

```python
# Bad in Python
pageCount = 5

# Good
page_count = 5
should_update = True
```

```go
// Bad in Go
const PAGE_COUNT = 5
var page_count = 5

// Good
const PageCount = 5 // exported
var pageCount = 5   // unexported
```

Map a schema's names at the boundary instead of letting them leak inward:

```ts
const user = { firstName: row.first_name } // map once, at the edge
```

```go
type User struct {
    FirstName string `json:"first_name"` // struct tag keeps the wire name
}
```

```python
class User(BaseModel):
    first_name: str = Field(alias="firstName")  # wire name is camelCase
```

## 3. Use short, intuitive, descriptive names

A name must be:

- **Short:** easy to type and remember.
- **Intuitive:** reads naturally.
- **Descriptive:** states the purpose or value.

```ts
/* Bad */
const a = 5 // "a" could mean anything
const isPaginatable = a > 10 // "Paginatable" sounds extremely unnatural
const shouldPaginatize = a > 10 // made-up verbs are bad

/* Good */
const postCount = 5
const hasPagination = postCount > 10
const shouldPaginate = postCount > 10 // alternatively
```

```python
post_count = 5
has_pagination = post_count > 10
```

```go
postCount := 5
hasPagination := postCount > 10
```

Booleans read as yes-or-no questions: `is`, `has`, `should`, `can`, `was`
(`is_active`, `hasPagination`, `canEdit`). In Go, short names are fine in a
small scope (`i`, `r` for a reader, `ctx`). Longer-lived names stay
descriptive.

## 4. Avoid abbreviations

Do not shorten words when the full name stays clear and practical.

```ts
/* Bad */
const onItmClk = () => {}

/* Good */
const onItemClick = () => {}
```

```python
# Bad
def calc_usr_tot(usr): ...

# Good
def calculate_user_total(user): ...
```

Widely known abbreviations are fine: `id`, `url`, `http`, `json`, `db`,
`config`, `max`, `min`, plus the language's own idioms such as Go's `ctx`,
`err` and `req`. Spell everything else out.

## 5. Avoid context duplication

A name should not repeat the context it is defined in. Remove the context from
a name whenever doing so doesn't make it less readable.

```ts
class MenuItem {
  /* Bad: method name duplicates the context (which is "MenuItem") */
  handleMenuItemClick = (event) => { ... }

  /* Good: reads nicely as `MenuItem.handleClick()` */
  handleClick = (event) => { ... }
}
```

```python
class MenuItem:
    def handle_click(self, event): ...   # not handle_menu_item_click
```

```go
package user

func Get(id string) (*User, error)   // called as user.Get(...), not user.GetUser(...)
type Store struct{}                   // user.Store, not user.UserStore
```

Packages and modules count as context too:

- Go package names prefix every use (`http.Server`, not `http.HTTPServer`).
- Python modules are often imported whole (`session.create`, not
  `session.create_session`).

## 6. Reflect the expected result

A name should state the result its value represents, so code using it reads
without negation.

```ts
/* Bad */
const isEnabled = itemCount > 3
return <Button disabled={!isEnabled} />

/* Good */
const isDisabled = itemCount <= 3
return <Button disabled={isDisabled} />
```

```python
# Good
is_expired = now - session.last_seen >= IDLE_TIMEOUT
if is_expired:
    raise SessionExpired("session_expired")
```

## 7. Name functions by action and context

Use this pattern:

`prefix? + action (A) + high context (HC) + low context? (LC)`

The prefix and the low context are optional.

- **Action:** the verb that states what the function does (`get`, `set`,
  `create`, `remove`, `handle`, `validate`, `parse`, `compute`).
- **Context:** the subject or data type. The high context is the most specific
  part.
- **Prefix:** use one only to disambiguate or add meaning (`should`, `is`,
  `has`, `can`, `try`, `must`).

| Name | Prefix | Action | High context | Low context |
|---|---|---|---|---|
| `getUser` | | get | User | |
| `getUserMessages` | | get | User | Messages |
| `handleClickOutside` | | handle | Click | Outside |
| `shouldDisplayMessage` | should | Display | Message | |

```ts
/* Bad */
const click = (event) => { ... } // action is not clear, high context is missing

/* Good */
// prefix: should, action: Display, high context: Message
const shouldDisplayMessage = (event) => { ... }

// action: get, high context: User, low context: Messages
const getUserMessages = () => { ... }
```

```python
def should_display_message(event): ...
def get_user_messages(): ...
```

```go
func shouldDisplayMessage(e Event) bool { ... }
func (s *Store) UserMessages(userID string) []Message { ... } // Go drops "get" for getters
```

Language notes:

- **Go** getters drop `get` (`Owner()`, not `GetOwner()`; setters stay
  `SetOwner`).
- **Rust** getters also drop `get` (`len()`, `name()`). `into_` and `as_`
  follow the standard conversion conventions.
- **Python** properties are nouns (`user.full_name`, not
  `user.get_full_name()`).
- **Constructors and factories** follow the language: `NewServer` in Go,
  `Server::new` in Rust, `create_server` or a class method in Python.

## 8. Match singular and plural names

Use plural names for collections and singular names for single entities.

```ts
/* Bad */
const friends = 'Bob'
const friend = ['Bob', 'Tony', 'Tanya']
const userList = getUser() // "userList" implies multiple users, but the function returns a single user

/* Good */
const friend = 'Bob'
const friends = ['Bob', 'Tony', 'Tanya']
const user = getUser()
const users = getUsers()
```

```python
friend = "Bob"
friends = ["Bob", "Tony", "Tanya"]
user = get_user()
users = get_users()
```

For maps and dictionaries, name both sides: `usersById` or `users_by_id`, and
`priceBySku`.

## How specmaker applies this

| Phase | What to do |
|---|---|
| propose | Fix every new public name in the LLD: modules, types, functions, fields, config keys, error codes, files. List them in §4 Interfaces, §3 Data Model and §12 File Boundary. Any repository rule that departs from this guide goes in `project.md` → Conventions |
| accredit | The readiness reviewer flags names left to the implementer. The critic flags names that break this guide without a reason |
| sprint | Use the names the LLD fixed, exactly. New private names follow this guide. Renaming a public name the LLD fixed is a deviation |
| sprint (verify) | The verifier reports naming breaks in changed code as Nit findings, or Major when a public API or contract is affected |

Spec requirement IDs, scenario IDs, change IDs and capability paths follow
`conventions.md` §6, not this file.
