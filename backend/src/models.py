import boto3


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
