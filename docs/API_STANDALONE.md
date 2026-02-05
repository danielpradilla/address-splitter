# Standalone API usage (Option A: Cognito JWT)

Goal: call the API without the web UI by obtaining a Cognito token and sending it as:

```
Authorization: Bearer <ID_TOKEN>
```

## Prereqs
- Deployed stack in **eu-central-1**
- A Cognito user exists (admin-created) and has set a password.

You will need these values (from CloudFormation outputs):
- `COGNITO_USER_POOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `API_BASE_URL`

## Get a token (AWS CLI)
This uses the USER_PASSWORD_AUTH flow.

```bash
aws cognito-idp initiate-auth \
  --region eu-central-1 \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id "$COGNITO_APP_CLIENT_ID" \
  --auth-parameters USERNAME="$EMAIL",PASSWORD="$PASSWORD" \
  --query 'AuthenticationResult.IdToken' \
  --output text
```

Store it:
```bash
export ID_TOKEN="$(...)"
```

## Call the API
### Models
```bash
curl -s "$API_BASE_URL/models" \
  -H "Authorization: Bearer $ID_TOKEN" | jq
```

### Update prompt
```bash
curl -s -X PUT "$API_BASE_URL/prompt" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt_template":"take the {country} and split: {address}"}' | jq
```

### Split
```bash
curl -s -X POST "$API_BASE_URL/split" \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "country_code":"DE",
    "raw_address":"Unter den Linden 77\n10117 Berlin\nGermany",
    "modelId":"<pick-from-/models>"
  }' | jq
```

### Recent
```bash
curl -s "$API_BASE_URL/recent?limit=10" \
  -H "Authorization: Bearer $ID_TOKEN" | jq
```

## Security notes
- Do not commit tokens, passwords, or `.env` files to git.
- Prefer using environment variables and your local shell history settings.
