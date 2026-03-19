import csv
import io
import json
from typing import Any

from address_resolver import choose_best_pipeline, corrected_address_full, default_pipelines, resolve_address
from prompting import render_prompt, validate_template
from prompt_defaults import DEFAULT_PROMPT_TEMPLATE


REQUIRED_INPUT_COLUMNS = ["raw_address"]
OPTIONAL_INPUT_COLUMNS = ["record_id", "country_code"]
OUTPUT_APPEND_COLUMNS = [
    "resolved_pipeline",
    "resolved_confidence",
    "resolved_warnings",
    "resolved_address_line1",
    "resolved_address_line2",
    "resolved_postcode",
    "resolved_city",
    "resolved_state_region",
    "resolved_country_code",
    "resolved_latitude",
    "resolved_longitude",
    "corrected_address_full",
    "pipeline_results_json",
]


def _stringify_warnings(warnings: list[Any] | Any) -> str:
    if isinstance(warnings, list):
        return "; ".join(str(w) for w in warnings if str(w).strip())
    if warnings is None:
        return ""
    return str(warnings)


def process_batch_csv_text(
    *,
    csv_text: str,
    model_id: str,
    pipelines: list[str] | None,
    prompt_template: str | None,
    pricing: dict[str, Any] | None,
    runtime_cfg: dict[str, str],
    default_country_code: str = "",
) -> tuple[str, dict[str, Any]]:
    prompt_template = (prompt_template or "").strip() or DEFAULT_PROMPT_TEMPLATE
    validate_template(prompt_template)

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("batch_input_missing_header")

    missing = [col for col in REQUIRED_INPUT_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise ValueError(f"batch_input_missing_columns:{','.join(missing)}")

    output = io.StringIO()
    fieldnames = list(reader.fieldnames) + [c for c in OUTPUT_APPEND_COLUMNS if c not in reader.fieldnames]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    processed = 0
    failed = 0

    for row in reader:
        processed += 1
        raw_address = (row.get("raw_address") or "").strip()
        country_code = (row.get("country_code") or default_country_code or "").strip().upper()

        if not raw_address:
            failed += 1
            out_row = dict(row)
            out_row.update(
                {
                    "resolved_pipeline": "",
                    "resolved_confidence": "0",
                    "resolved_warnings": "missing_raw_address",
                    "resolved_address_line1": "",
                    "resolved_address_line2": "",
                    "resolved_postcode": "",
                    "resolved_city": "",
                    "resolved_state_region": "",
                    "resolved_country_code": country_code,
                    "resolved_latitude": "",
                    "resolved_longitude": "",
                    "corrected_address_full": "",
                    "pipeline_results_json": json.dumps(
                        {"error": "missing_raw_address"},
                        ensure_ascii=False,
                    ),
                }
            )
            writer.writerow(out_row)
            continue

        rendered_prompt = render_prompt(
            prompt_template,
            country=country_code,
            address=raw_address,
        )
        results = resolve_address(
            country_code=country_code,
            raw_address=raw_address,
            model_id=model_id,
            pipelines=pipelines or default_pipelines(),
            rendered_prompt=rendered_prompt,
            pricing=pricing or {},
            **runtime_cfg,
        )
        best_pipeline = choose_best_pipeline(results)
        best_result = results.get(best_pipeline) or {}

        out_row = dict(row)
        out_row.update(
            {
                "resolved_pipeline": best_pipeline,
                "resolved_confidence": best_result.get("confidence", ""),
                "resolved_warnings": _stringify_warnings(best_result.get("warnings") or []),
                "resolved_address_line1": best_result.get("address_line1", ""),
                "resolved_address_line2": best_result.get("address_line2", ""),
                "resolved_postcode": best_result.get("postcode", ""),
                "resolved_city": best_result.get("city", ""),
                "resolved_state_region": best_result.get("state_region", ""),
                "resolved_country_code": best_result.get("country_code", ""),
                "resolved_latitude": best_result.get("latitude", ""),
                "resolved_longitude": best_result.get("longitude", ""),
                "corrected_address_full": corrected_address_full(best_result),
                "pipeline_results_json": json.dumps(results, ensure_ascii=False),
            }
        )
        writer.writerow(out_row)

    return output.getvalue(), {"rows_processed": processed, "rows_failed": failed}
