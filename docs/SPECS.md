# Address Splitter (AWS Bedrock) — Specs

## 1) Problem / Goal
Users enter:
- **Name** (single field)
- **Country** (selection)
- **Free-text address** (multi-line)

The app supports **3 side-by-side pipelines** to split + geocode an address, and stores the results for comparison:

1. **LLM (AWS Bedrock) + downloaded GeoNames**
2. **libpostal (Senzing libpostal data model) + downloaded GeoNames**
   - Implemented via **Lambda container image** (native libpostal + Python bindings).
3. **AWS services** (Amazon Location Service for geocoding + structured components)

The goal is to compare accuracy/cost and choose a preferred output.

Primary output fields (baseline):
- `recipient_name`
- `country_code` (ISO-3166-1 alpha-2)
- `address_line1` (street + number)
- `address_line2` (apt/unit/building, etc.)
- `postcode`
- `city`
- `state_region` (state/province/canton/region)
- `neighborhood` (optional)
- `po_box` (optional)
- `company` (optional)
- `attention` / `c_o` (optional)
- `raw_address` (echo)
- `confidence` (0–1)
- `warnings[]` (strings; e.g., ambiguous postcode/city)

Optional enrichment (v1):
- `latitude`
- `longitude`
- `geo_accuracy` (`street|postcode|city|none`)
- `geonames_match` (optional short string)

GeoNames enrichment logic (current):
- If we have `country_code` + `postcode`: lookup postcode centroid from offline GeoNames.
- Else if we have `country_code` + `city`: 
  - pick the **most populated** city match (offline GeoNames cities table)
  - if multiple postcodes match the city, pick the postcode centroid **closest** to the selected city centroid.
- Name matching uses normalization: casefolding, ASCII folding (strip accents), punctuation removal, and whitespace collapsing.

Non-goals (v1):
- Full postal validation against carrier databases
- Carrier-grade address validation (deliverability), rooftop guarantees
- Duplicate detection

## 2) Users & UX
### 2.1 Flow
1. User opens web page and signs in.
2. User enters Name, chooses Country, pastes free-text address.
3. User selects:
   - Bedrock model (used by pipeline #1)
   - which pipelines to run (default: all 3)
4. User can edit the **Prompt Template** (used by pipeline #1).
5. Click **Split Address**.
6. UI shows **3 results side-by-side** (one per pipeline):
   - structured fields
   - lat/long + accuracy
   - confidence + warnings
   - raw JSON (collapsible)
7. User can mark one pipeline result as **Preferred** (stored).
8. UI also shows **“Recent (last 10)”** submissions for the signed-in user; each recent item links to its saved side-by-side comparison.

### 2.2 UX requirements
- Responsive (mobile + desktop)
- Fast first load (static hosting)
- Clear error messages (permissions, model unavailable, throttling)
- Prompt template editor (pipeline #1):
  - Supports variable placeholders: `{name}`, `{country}`, `{address}`
  - Shows a live “Rendered prompt” preview
  - Persisted per-user across sessions
  - First run gets a sensible default prompt (demo prompt)
- Side-by-side compare UI:
  - show 3 columns consistently
  - highlight differences between pipelines (nice-to-have)
  - allow selecting a **Preferred** pipeline result

## 3) Architecture (cheapest reasonable)

Deployment defaults:
- AWS region: **eu-central-1**
- Cognito Hosted UI domain prefix (recommended): **`danielpradilla-address-splitter`** (parameterized)

### 3.1 High-level
- **Frontend:** Static site hosted on **S3** + **CloudFront**
- **Backend API:** **API Gateway HTTP API** → **Lambda**
- **Pipeline #1 (LLM):** AWS Bedrock `InvokeModel` (+ `ListFoundationModels`)
- **Pipeline #2 (libpostal):** libpostal parsing in Lambda **container image** (native deps) using the **Senzing data model**.
- **Pipeline #3 (AWS services):** Amazon Location Service Place Index (geocode + structured components)
- **GeoNames (offline):** downloaded GeoNames datasets loaded into DynamoDB lookup tables (used by #1 and #2)
  - Postcodes table: `...-geonames` (PK = `CC#POSTCODE`)
  - Cities table (population-ranked): `...-geonames-cities` (PK = `CC#<normalized city>`, SK = `POP#...`)
  - Postcodes table also includes a GSI for city→postcode lookup: `GSI2PK = CC#<normalized place_name>`, `GSI2SK = <postcode>`
- **Storage:** DynamoDB to store the submission and all three pipeline results + TTL
- **Auth:** Cognito User Pool (email/password, admin-created users only) + Hosted UI + JWT authorizer

V1 recommendation: ship **with Cognito auth enabled by default**. Keep a CloudFormation switch to disable auth only for private testing.

### 3.2 Data flow
Browser → `POST /split` with `{name,country,address,modelId}` → Lambda:
- builds prompt & JSON schema
- calls Bedrock model
- validates JSON output
- returns normalized object

Browser → `GET /models` → Lambda:
- calls `bedrock:ListFoundationModels` (and optionally filters to “text” / “chat” models)
- returns list of `{modelId, providerName, modelName}`

Browser → `POST /split` persists the result to DynamoDB (by default).
- If geocoding is enabled, backend enriches the split result using offline GeoNames and persists lat/long.
Browser → `GET /recent?limit=10` fetches the most recent items for the signed-in user.
(Optional) Browser → `DELETE /recent/{id}` to remove an item.
Browser → `GET /prompt` returns the user’s saved prompt template; if none exists, returns the **default demo prompt**.
Browser → `PUT /prompt` saves the user’s prompt template.

## 4) API Spec
Base URL: CloudFront → API Gateway (or direct API Gateway URL in dev)

Standalone usage:
- Supported (Option A): obtain Cognito JWT via CLI and call API with `Authorization: Bearer <JWT>`.
- See `docs/API_STANDALONE.md`.

### 4.0 Authentication
All endpoints require:
- `Authorization: Bearer <JWT>` (Cognito **ID token** is fine for this app)

Session behavior (SPA):
- Frontend uses OAuth2 Authorization Code + PKCE.
- Cognito refresh tokens are configured to last **30 days**.
- The frontend will automatically refresh tokens (using `refresh_token`) when an API call returns `401`.

User management policy (v1):
- **No public registration** (no open sign-up).
- Users are **created by an admin** (invite flow), then they set a password.

Unauthenticated requests return `401`.

### 4.1 `GET /models`
Response 200:
```json
{
  "models": [
    {"modelId": "anthropic.claude-3-5-sonnet-20240620-v1:0", "provider": "Anthropic", "name": "Claude 3.5 Sonnet"}
  ]
}
```
Notes:
- Filter out embedding/image models.
- Sort by provider/name.

### 4.2 `POST /split`
Runs the selected pipelines (default all 3), stores the comparison, and returns the side-by-side results.

Request:
```json
{
  "recipient_name": "Jane Doe",
  "country_code": "CH",
  "raw_address": "Rue du Rhône 10\n1204 Genève\nSuisse",
  "modelId": "anthropic.claude-3-5-sonnet-20240620-v1:0",
  "pipelines": ["bedrock_geonames","libpostal_geonames","aws_services"]
}
```

Response 200:
```json
{
  "submission_id": "01JH2...",
  "created_at": "2026-02-03T08:57:00Z",
  "user_sub": "cognito-sub",
  "input": {
    "recipient_name": "Jane Doe",
    "country_code": "CH",
    "raw_address": "Rue du Rhône 10\n1204 Genève\nSuisse",
    "modelId": "anthropic..."
  },
  "results": {
    "bedrock_geonames": {"address_line1":"...","postcode":"...","latitude":46.2,"longitude":6.14,"geo_accuracy":"postcode","confidence":0.86,"warnings":[]},
    "libpostal_geonames": {"address_line1":"...","postcode":"...","latitude":46.2,"longitude":6.14,"geo_accuracy":"postcode","confidence":0.65,"warnings":[]},
    "aws_services": {"address_line1":"...","postcode":"...","latitude":46.2,"longitude":6.14,"geo_accuracy":"street","confidence":0.9,"warnings":[]}
  },
  "preferred_method": null
}
```

Errors:
- 400: validation error (missing fields, unsupported country code)
- 401: unauthorized
- 429: throttled
- 500: pipeline failure (details in logs)

### 4.3 `GET /prompt`
Returns the saved prompt template for the signed-in user.

Response 200:
```json
{
  "prompt_template": "... {country} ... {address} ...",
  "is_default": false,
  "updated_at": "2026-02-03T08:57:00Z"
}
```
Notes:
- If the user has no saved prompt yet, return the default demo prompt with `is_default=true`.

### 4.4 `PUT /prompt`
Saves the prompt template for the signed-in user.

Request:
```json
{ "prompt_template": "take the {country} and then split {address}" }
```
Response 200:
```json
{ "ok": true }
```
Validation:
- Must include `{address}`.
- May include `{country}` and `{name}`.

### 4.5 `GET /recent?limit=10`
Returns the most recent **submissions** for the signed-in user.

Response 200:
```json
{
  "items": [
    {
      "submission_id": "01JH2...",
      "created_at": "2026-02-03T08:57:00Z",
      "country_code": "CH",
      "recipient_name": "Jane Doe",
      "raw_address_preview": "Rue du Rhône 10, 1204 Genève",
      "preferred_method": "bedrock_geonames"
    }
  ]
}
```

### 4.6 `GET /submission/{id}`
Fetch one stored submission including all pipeline results.

### 4.7 `PUT /submission/{id}/preferred`
Set `preferred_method` to one of: `bedrock_geonames|libpostal_geonames|aws_services`.

### 4.8 CORS
- Allow origins: configurable parameter (default `*` for dev)
- Allow methods: `GET,POST,PUT,OPTIONS`

## 5) Data model (DynamoDB)

### 5.1 Submissions table (stores side-by-side results)
Table: `AddressSplitterSubmissions`

Keys:
- `PK` (string): `USER#<cognito_sub>`
- `SK` (string): `SUB#<submission_id>`

Attributes (stored):
- `submission_id` (ULID)
- `created_at` (ISO8601)
- `user_sub`
- `ttl` (number, epoch seconds)
- `input`: `{recipient_name,country_code,raw_address,modelId}`
- `results`: map keyed by pipeline id (each result includes `source` and `method`):
  - `bedrock_geonames` (`source`: `bedrock`, `geocode`: `geonames_offline`)
  - `libpostal_geonames` (`source`: `libpostal`, `geocode`: `geonames_offline`)
  - `aws_services` (`source`: `amazon_location`, `geocode`: `amazon_location`)
- `preferred_method` (nullable)

Index fields (for recents):
- `GSI1PK`: `USER#<cognito_sub>`
- `GSI1SK`: `TS#<created_at>#SUB#<submission_id>`

Notes:
- Each pipeline result stores the standard split fields plus optional geocoding fields (`latitude`,`longitude`,`geo_accuracy`,`geonames_match`).

Access patterns:
- List recents: `Query` by `GSI1PK = USER#<cognito_sub>` sorted by `GSI1SK = TS#<created_at>#SUB#<submission_id>` (descending)
- Fetch one: `GetItem` by `PK`+`SK`

Retention:
- Default: **30 days** (configurable)

### 5.2 User settings table (prompt template)
Table: `AddressSplitterUserSettings`

Keys:
- `user_sub` (string) — partition key

Attributes:
- `prompt_template` (string)
- `updated_at` (ISO8601)

Behavior:
- If no row exists for the user, backend serves a **default demo prompt**.

## 6) Address parsing contract
### 5.1 Output JSON schema (informal)
- Always return a JSON object.
- Required: `recipient_name`, `country_code`, `raw_address`, `confidence`, `warnings`.
- Others may be empty strings if not present.

### 6.2 Prompting approach
Use a **prompt template** stored per user (editable in UI).

Template variables:
- `{name}` → recipient name field
- `{country}` → country selection (use ISO-2 code or label; pick one and be consistent)
- `{address}` → free-text address

Rules:
- Backend renders the template and sends the rendered prompt to Bedrock.
- The UI displays:
  - the template
  - the rendered prompt (preview)

A default demo prompt is used on first run (see `docs/_prompt_demo.txt`).

### 6.3 Post-processing
Lambda should:
- JSON-parse model output
- enforce keys and types
- clamp confidence to `[0,1]`
- optionally run light heuristics (e.g., if postcode embedded in city)

## 7) Security, Privacy, Observability
- Treat address as **PII**.

### 7.1 Authentication & transport security
- **No passwords in the app**: passwords are handled only by **Cognito Hosted UI** over HTTPS.
- Frontend uses **OAuth2 Authorization Code + PKCE** to sign in.
- API calls use `Authorization: Bearer <JWT>`; API Gateway enforces auth via **JWT authorizer**.
- Enforce **HTTPS only** and add **HSTS** headers via CloudFront Response Headers Policy.

### 7.2 "Safe for GitHub" (no secrets committed)
- Do not commit:
  - AWS credentials (`~/.aws/*`)
  - Cognito app client secrets (prefer **no client secret** for SPA)
  - any API keys / admin passwords
- Store runtime configuration as CloudFormation outputs + environment variables:
  - `API_BASE_URL`
  - `COGNITO_USER_POOL_ID`
  - `COGNITO_APP_CLIENT_ID`
  - `COGNITO_DOMAIN`
  - `COGNITO_REDIRECT_URI`
- If any secret is required later (avoid in SPA): store in **SSM Parameter Store** or **Secrets Manager**, not in repo.

### 7.3 Abuse prevention
- API Gateway throttling (per-stage) and request size limits.
- Keep the API behind Cognito JWT auth (no public endpoints).

### 7.4 Data isolation & logging hygiene
- **Storage isolation:** items are partitioned by the signed-in user (Cognito `sub`).
- Do not log raw addresses or tokens by default.
  - log only `requestId`, timings, status codes
  - optional debug flag in CloudFormation to enable masked logging

### 7.5 IAM least privilege
- Lambda role:
  - DynamoDB: `PutItem`, `GetItem`, `UpdateItem`, `Query` on submissions + user settings + GeoNames tables (and GeoNames postcodes GSI).
  - Bedrock: `InvokeModel` (+ model listing).
  - Amazon Location: `geo:SearchPlaceIndexForText`.
  - Marketplace (some Bedrock inference profiles): `aws-marketplace:ViewSubscriptions`, `aws-marketplace:Subscribe`.

Notes:
- Amazon Location `FilterCountries` expects ISO-3; the app country context is ISO-2. The backend maps ISO-2 → ISO-3 (via `iso3166`) before calling Amazon Location.

### 7.6 Retention
- CloudWatch logs retention: parameterized (default 14 days)

## 8) Cost considerations
Cost fields:
- API returns `cost.estimated_cost_usd` as a floating value rounded to **9 decimals**.
- DynamoDB does not support float types via boto3; we store floats as **strings** when persisting submissions (keeping ~12 decimal places).

- S3 + CloudFront static hosting: cents/month at low traffic.
- API Gateway HTTP API + Lambda: pay per request.
- Bedrock: dominates cost; expose model choice so user can pick cheaper models.
- **DynamoDB TTL**: auto-deletes old items so storage doesn’t grow indefinitely.
- CI/CD: CodePipeline/CodeBuild have small per-minute costs when running builds.
- Add per-IP throttling via API Gateway.

## 9) Tech choices (scaffold defaults)
- **Backend:** Python 3.12 Lambda
- **IaC:** CloudFormation (YAML)
- **Frontend:** Vanilla HTML/CSS/JS (no framework) for lowest complexity/cost
  - light theme only (simpler)
  - palette: `["#22223b","#4a4e69","#9a8c98","#c9ada7","#f2e9e4"]`
  - optional upgrade path: React/Vite
- **CI/CD:** AWS **CodePipeline + CodeBuild** (Option 1)
  - GitHub (via CodeStar Connection) → CodeBuild runs `buildspec.yml`
  - Deploy CloudFormation + sync frontend to S3 + invalidate CloudFront on every commit to main
  - All sensitive values provided via CloudFormation parameters / outputs / environment variables (safe for GitHub)

## 10) Repo / folder layout
```
address-splitter/
  docs/
    SPECS.md
    TASKS.md
    API_STANDALONE.md
  infra/
    cloudformation/
      main.yaml
      pipeline.yaml
      parameters.example.json
  backend/
    src/
      app.py
      bedrock.py
      schemas.py
  frontend/
    index.html
    app.js
    styles.css
  buildspec.yml
```

## 11) Acceptance criteria
- User can open the webpage, sign in, and submit an address.
- UI shows **3 side-by-side results** (Bedrock+GeoNames, libpostal+GeoNames, AWS services) and stores them.
- Model dropdown shows Bedrock text/chat models accessible in the account/region (used by pipeline #1).
- User can view recents and open a stored submission comparison.
- User can mark a preferred pipeline.
- CloudFormation deploys end-to-end with a single command.
- No raw address or tokens are written to logs by default.
