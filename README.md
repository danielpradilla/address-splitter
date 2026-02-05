# address-splitter

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
3. **AWS services** (Amazon Location Service for geocoding + structured components)

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

3. Load env vars and deploy:

```bash
source .env.local
chmod +x scripts/deploy-pipeline.sh
./scripts/deploy-pipeline.sh
```

Notes:
- `.env.local` is ignored by git.
- `.env.example` is safe to commit.

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
