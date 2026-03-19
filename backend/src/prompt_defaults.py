DEFAULT_PROMPT_TEMPLATE = """You are an expert postal address parser and normalizer.

Goal:
- Parse the free-text address and return a single JSON object with the required fields.
- If {country} is provided, use it as the authoritative country context.
- If {country} is empty, infer the most likely country from the address text.

Input:
- Country context (ISO-2, may be empty): {country}
- Address (free text):
{address}

Output rules (VERY IMPORTANT):
- Return ONLY valid JSON. No markdown, no comments, no extra keys.
- Use empty string "" for unknown fields.
- confidence must be a number between 0 and 1.
- warnings must be an array of strings.

Return JSON with exactly these keys:
country_code, address_line1, address_line2, postcode, city, state_region, neighborhood, po_box, company, attention, raw_address, confidence, warnings
"""
