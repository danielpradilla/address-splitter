import boto3


def list_inference_profiles(region: str | None = None) -> list[dict]:
    client = boto3.client("bedrock", region_name=region)

    # API name is list_inference_profiles in boto3
    resp = client.list_inference_profiles()

    profiles = []
    for p in resp.get("inferenceProfileSummaries", []) or []:
        arn = p.get("inferenceProfileArn")
        pid = p.get("inferenceProfileId")
        name = p.get("inferenceProfileName") or pid or arn
        if not arn:
            continue
        profiles.append(
            {
                "id": pid or "",
                "arn": arn,
                "name": name,
                "type": p.get("type") or "",
                "status": p.get("status") or "",
            }
        )

    profiles.sort(key=lambda x: (x.get("type", ""), x.get("name", "")))
    return profiles


def list_bedrock_models(region: str | None = None) -> list[dict]:
    # Use the Bedrock control plane client.
    client = boto3.client("bedrock", region_name=region)
    resp = client.list_foundation_models()

    models = []
    for m in resp.get("modelSummaries", []) or []:
        mid = m.get("modelId")
        if not mid:
            continue

        # Filter out non-text models; keep it conservative.
        # Bedrock returns various types; we keep only "TEXT" and "CHAT" style where available.
        out_mods = set((m.get("outputModalities") or []))
        if out_mods and not (out_mods & {"TEXT"}):
            continue

        models.append(
            {
                "modelId": mid,
                "provider": m.get("providerName") or "",
                "name": m.get("modelName") or mid,
            }
        )

    models.sort(key=lambda x: (x["provider"], x["name"]))
    return models
