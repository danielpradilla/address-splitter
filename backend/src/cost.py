def estimate_tokens(text: str) -> int:
    # Rough heuristic: ~4 chars per token for English-ish text.
    # Good enough for relative comparisons.
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def estimate_bedrock_cost_usd(*, prompt: str, output_text: str, in_per_m: float, out_per_m: float) -> dict:
    in_tokens = estimate_tokens(prompt)
    out_tokens = estimate_tokens(output_text)
    cost = (in_tokens / 1_000_000.0) * in_per_m + (out_tokens / 1_000_000.0) * out_per_m
    return {
        "input_tokens_est": in_tokens,
        "output_tokens_est": out_tokens,
        "estimated_cost_usd": round(cost, 6),
        "basis": "char_heuristic_v1",
    }


def estimate_location_cost_usd(*, per_request: float) -> dict:
    return {
        "estimated_cost_usd": round(float(per_request), 6),
        "basis": "per_request",
    }
