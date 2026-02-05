# Address Splitter — Build Tasks

## Phase 0 — Decisions (fast)
1. Confirm AWS region to deploy: **eu-central-1**.
2. **Auth (v1): Cognito User Pool (email/password), admin-created users only**.
3. Storage: DynamoDB on-demand.
4. Pipelines to implement (v1):
   - #1 Bedrock + downloaded GeoNames
   - #2 libpostal + downloaded GeoNames
   - #3 AWS services (Amazon Location)

## Phase 1 — Project scaffolding
1. Create repo/folder structure:
   - `infra/cloudformation/`
   - `backend/src/`
   - `frontend/`
   - `docs/`
2. Add basic project files:
   - `README.md` (how to deploy/run)
   - `.gitignore`

## Phase 2 — CloudFormation (infra)
1. Create `infra/cloudformation/main.yaml` with parameters:
   - `AppName`
   - `Stage` (dev/prod)
   - `AllowedOrigins`
   - `LogRetentionDays`
   - `ResultsRetentionDays` (default 30)
   - `CognitoDomainPrefix` (default `danielpradilla-address-splitter`)
   - `EnableGeonamesOffline` (default true)
   - `EnableLibpostal` (default true)
   - `EnableAwsServices` (default true)
   - `GeonamesDataS3Uri` (optional; e.g. `s3://<bucket>/geonames/`)
2. Resources:
   - S3 bucket for frontend
   - CloudFront distribution (origin: S3)
   - API Gateway HTTP API
   - Lambda function + IAM role
   - Lambda permissions for API Gateway
   - CloudWatch log group (with retention)
   - Cognito User Pool (email/password) + app client + domain (Hosted UI) + JWT authorizer
   - DynamoDB table for submissions/results (on-demand) + **TTL enabled** (attribute: `ttl`) + **GSI for recents**:
     - `GSI1PK = USER#<cognito_sub>`
     - `GSI1SK = TS#<created_at>#SUB#<submission_id>`
   - DynamoDB table for user settings (prompt template)
   - DynamoDB table(s) for GeoNames lookups + S3 bucket/prefix for dataset files
   - Amazon Location Service Place Index (for pipeline #3)
3. GeoNames data ingestion (offline):
   - download GeoNames postal code dataset(s)
   - upload raw files to S3 at `GeonamesDataS3Uri`
   - run an import job (script or one-off Lambda) to load lookup records into DynamoDB
   - document the expected key scheme (e.g., `COUNTRY#POSTCODE`)
4. libpostal packaging:
   - build Lambda container image (recommended) that includes libpostal + Python bindings
   - publish to ECR and reference from CloudFormation when `EnableLibpostal=true`
5. Outputs:
   - CloudFront URL
   - API base URL
   - (Optional) Cognito details

## Phase 3 — Backend: Lambda API
1. Implement routes (single Lambda handler):
   - `GET /models` (Bedrock)
   - `GET /prompt` / `PUT /prompt` (Bedrock prompt template)
   - `POST /split` (runs 1–3 pipelines, stores all results)
   - `GET /recent?limit=10`
   - `GET /submission/{id}` (fetch stored side-by-side results)
   - `PUT /submission/{id}/preferred` (store preferred pipeline)
2. Implement Bedrock client calls:
   - `ListFoundationModels` (filter to text/chat)
   - `InvokeModel` (support multiple providers)
2b. Implement Amazon Location client calls (pipeline #3):
   - `SearchPlaceIndexForText`
3. Implement pipeline execution + persistence:
   - Create a `submission_id` (ULID) per request.
   - Run selected pipelines and store outputs under that submission.

   Pipeline #1 (Bedrock + GeoNames):
   - load prompt template; validate + render with `{name}`, `{country}`, `{address}`
   - call Bedrock; parse/validate JSON
   - geocode via offline GeoNames (prefer `(country_code, postcode)` fallback `(country_code, city)`)

   Pipeline #2 (libpostal + GeoNames):
   - parse free-text using libpostal
   - map to target schema
   - geocode via offline GeoNames

   Pipeline #3 (AWS services):
   - call Amazon Location Service Place Index search for the raw address (country constrained)
   - map provider response into target schema + lat/lon
   - set `geo_accuracy` based on match quality (street vs city)

   Persistence:
   - write a single DynamoDB item containing:
     - user_sub, created_at, ttl
     - input (name,country,address,chosen model)
     - `results`: map keyed by `bedrock_geonames`, `libpostal_geonames`, `aws_services`
     - `preferred_method` (nullable)
4. Add safe logging:
   - requestId
   - timings
   - no raw address logging
5. Add unit tests for:
   - JSON parsing
   - schema validation
   - error mapping

## Phase 4 — Frontend (static)
0. Apply UI styling (light theme only):
   - palette: `["#22223b","#4a4e69","#9a8c98","#c9ada7","#f2e9e4"]`
1. Add Cognito sign-in/out:
   - Use Cognito Hosted UI (OAuth2 code + PKCE)
   - Do **not** show any sign-up/registration UX (admin-created users only)
   - Store tokens in memory (or sessionStorage) and attach `Authorization: Bearer <token>` to API calls
2. Add prompt UI:
   - Fetch saved prompt via `GET /prompt` on load
   - Show editable textarea for the prompt template
   - Show a live “Rendered prompt” preview (substitute `{name}`, `{country}`, `{address}`)
   - Save button → `PUT /prompt`
   - On first run, show the demo prompt returned by API (`is_default=true`)
3. Build core UI:
   - Name input
   - Country select (show name + ISO-2)
   - Address textarea
   - Model select (populated via `/models`, used for pipeline #1)
   - Pipeline toggles (1/2/3; default all on)
   - Submit button
4. Render results (side-by-side):
   - 3 columns (pipeline #1/#2/#3)
   - structured fields
   - geocode (lat/lon + accuracy)
   - warnings/confidence
   - raw JSON toggle
   - show rendered Bedrock prompt (pipeline #1)
   - (Optional) "Mark preferred" button per column

4b. Improve Recent (last 10) UI:
   - Show structured fields per pipeline as separate columns: Street address, City, Postal Code, State/Region, Country.
   - Show warnings/alerts in a dedicated Alerts column.
   - Use smaller font and conditional background to visually indicate completeness (all key fields present).
5. Handle errors nicely (inline, not console-only).
6. Add a small “cost hint” (optional): allow user to pick smaller/cheaper models.

## Phase 5 — CI/CD (CodePipeline + CodeBuild)
1. Add `buildspec.yml` to:
   - run tests
   - package Lambda
   - `aws cloudformation deploy` the main stack (eu-central-1)
   - `aws s3 sync` the frontend to the hosting bucket
   - `aws cloudfront create-invalidation` on deploy
2. Create a CloudFormation template for the pipeline:
   - `infra/cloudformation/pipeline.yaml`
   - Uses **CodeStar Connection** to GitHub (provide `CodeStarConnectionArn`)
   - Source: GitHub
   - Build+Deploy: CodeBuild (runs `buildspec.yml`)
3. IAM:
   - CodePipeline role: S3 artifacts + StartBuild + UseConnection
   - CodeBuild role: CloudFormation deploy + S3 sync + CloudFront invalidation (+ service permissions for resources created)
4. Add an admin user provisioning doc/script:
   - `scripts/create_user.sh` (wraps `aws cognito-idp admin-create-user`)
   - document how the invited user sets their password
5. Keep local helper scripts optional for manual deploy.
6. Document CI/CD setup in `README.md`.

## Phase 6 — Hardening + "safe for GitHub" (recommended)
1. Ensure Cognito client is configured for SPA:
   - Authorization Code + PKCE
   - **no client secret**
2. Enforce HTTPS + HSTS:
   - CloudFront redirect HTTP→HTTPS
   - CloudFront Response Headers Policy (HSTS)
3. Add API protections:
   - API Gateway throttling settings + request size limits
   - Lambda request/response size safeguards
4. Repo hygiene:
   - `.gitignore` for `.env`, AWS creds, build artifacts
   - provide `frontend/config.example.js` (or similar) with placeholders only
   - document how to set config via CloudFormation outputs

## Phase 7 — Acceptance & demo
1. Deploy to dev stage.
2. Run manual tests with:
   - US address
   - Swiss address
   - multi-line address with company/attention
   - ambiguous address (ensure warnings appear)
3. Verify:
   - `/models` works in region
   - No raw addresses in logs
4. Capture screenshots + short demo notes.
