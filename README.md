# address-splitter

## License
MIT (see `LICENSE`).

Experiment playground for **parsing / splitting / geocoding postal addresses** and comparing approaches side-by-side.

## What it does
- Simple web UI where you paste a free-text address (plus name + country)
- Runs **multiple pipelines** to split the address into structured fields
- Runs **geocoding** to produce latitude/longitude
- Stores results so you can review the **most recent submissions** and compare quality over time (Recent table shows key fields per pipeline + alerts, with completeness highlighting)

## Pipelines (side-by-side)
1. **LLM splitting (AWS Bedrock) + offline GeoNames geocoding**
   - If postcode is present: postcode centroid lookup.
   - If only city is present (and country is known): pick most-populated city match, then infer postcode (choosing the postcode centroid closest to the city centroid).
   - Matching is robust to accents/punctuation/case (ASCII-fold + normalization).
2. **libpostal splitting + offline GeoNames geocoding**
   - Implemented using **real libpostal** inside the API Lambda **container image**.
   - libpostal model is the **Senzing** data model (baked into the image).
   - Operational mode: **wake/sleep** (provisioned concurrency on demand) for sporadic usage.
3. **AWS services** (Amazon Location Service for geocoding + structured components)
4. **Loqate** (Capture Interactive Find → Retrieve for address parsing/normalization)
   - Uses Loqate to resolve a free-text address into structured components.
   - Cloud runtime: configure via AWS Secrets Manager (secret JSON key: `LOQATE_API_KEY`).
   - Local runtime: can use `LOQATE_API_KEY` in local env.

Each stored submission includes provenance so you always know which output came from which pipeline.

## Why
Addresses are messy. This repo is meant to help compare:
- accuracy
- cost
- failure modes
- operational complexity

## Sessions / staying signed in
- Cognito refresh tokens are configured to last **30 days**.
- The frontend will automatically refresh tokens when the ID token expires (on 401).

## Deployment
See `deployment.md` (kept local; ignored by git).

### Deploy pipeline without retyping parameters (local-only)
1. Copy the example env file:

```bash
cp .env.example .env.local
```

2. Edit `.env.local` if needed.
   - For cloud deploys, set `LOQATE_SECRET_ID` to your Secrets Manager secret id/name/ARN.
   - Secret JSON must contain `{"LOQATE_API_KEY":"..."}`.

3. Load env vars and deploy:

```bash
source .env.local
chmod +x scripts/deploy-pipeline.sh
./scripts/deploy-pipeline.sh
```

Notes:
- `.env.local` is ignored by git.
- `.env.example` is safe to commit.

### Configure Loqate API key
Use AWS Secrets Manager for cloud runtime.

1. Create (or update) a secret in `eu-central-1`:

```bash
aws secretsmanager create-secret \
  --region eu-central-1 \
  --name address-splitter/dev/loqate \
  --secret-string '{"LOQATE_API_KEY":"YOUR_LOQATE_KEY"}'
```

If it already exists, update the value:

```bash
aws secretsmanager put-secret-value \
  --region eu-central-1 \
  --secret-id address-splitter/dev/loqate \
  --secret-string '{"LOQATE_API_KEY":"YOUR_LOQATE_KEY"}'
```

2. Set the secret id in `.env.local`:

```bash
export LOQATE_SECRET_ID=address-splitter/dev/loqate
```

3. Deploy:

```bash
source .env.local
./scripts/deploy-pipeline.sh
```

Notes:
- Secret JSON key must be exactly `LOQATE_API_KEY`.
- Runtime Lambda env var `LOQATE_API_KEY` is injected from this secret by CloudFormation.
- If you rotate/update the secret value, redeploy the main app stack (or run the pipeline again) so Lambda picks up the new value.
- For local-only testing (outside AWS), you can export `LOQATE_API_KEY` directly in your shell.

### Wake/Sleep libpostal (sporadic usage)
`libpostal + Senzing` has heavy model-init cost. For low idle spend, use manual wake/sleep:

1. Wake before using pipeline `2) libpostal + GeoNames`:

```bash
source .env.local
chmod +x scripts/libpostal-wake.sh scripts/libpostal-sleep.sh
./scripts/libpostal-wake.sh
```

2. Use the app normally.

3. Sleep when done:

```bash
source .env.local
./scripts/libpostal-sleep.sh
```

Notes:
- Wake configures provisioned concurrency on Lambda alias `live`.
- Sleep removes provisioned concurrency (no always-on warm capacity).
- If libpostal is asleep, requests may fail or time out due to long cold init.

## Quick auth + API test (Cognito user required)
After you create a Cognito user (admin-created), you can verify auth + API reachability.

### Get an ID token
```bash
export AWS_REGION=eu-central-1
export COGNITO_APP_CLIENT_ID="<from CloudFormation output CognitoAppClientId>"
export EMAIL="you@example.com"
export PASSWORD="your-password"

export ID_TOKEN="$(aws cognito-idp initiate-auth \
  --region "$AWS_REGION" \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id "$COGNITO_APP_CLIENT_ID" \
  --auth-parameters USERNAME="$EMAIL",PASSWORD="$PASSWORD" \
  --query 'AuthenticationResult.IdToken' \
  --output text)"

echo "$ID_TOKEN" | head
```

### Call /health
```bash
export API_BASE_URL="<from CloudFormation output ApiBaseUrl>"

curl -s "$API_BASE_URL/health" \
  -H "Authorization: Bearer $ID_TOKEN"
```

## Repo layout
- `infra/` CloudFormation templates
- `backend/` Lambda source + Dockerfile (container image; includes libpostal)
- `frontend/` static site
- `docs/` additional docs (some files intentionally not tracked)
