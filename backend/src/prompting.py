import re

def render_prompt(template: str, *, name: str, country: str, address: str) -> str:
    # Strict, simple templating: only allow the known placeholders.
    # Prevent surprises by leaving unknown {things} untouched.
    name_v = (name or "").strip() or "(blank)"
    country_v = (country or "").strip().upper() or "(auto)"
    address_v = (address or "").strip()

    rendered = template
    rendered = rendered.replace("{name}", name_v)
    rendered = rendered.replace("{country}", country_v)
    rendered = rendered.replace("{address}", address_v)

    # Cleanup: collapse repeated spaces (but keep newlines as-is)
    rendered = "\n".join(" ".join(line.split()) for line in rendered.splitlines())
    return rendered.strip()


def validate_template(template: str) -> None:
    if "{address}" not in template:
        raise ValueError("prompt_template must include {address}")

    # Optional: flag unknown placeholders
    allowed = {"name", "country", "address"}
    for var in re.findall(r"\{([a-zA-Z0-9_]+)\}", template):
        if var not in allowed:
            raise ValueError(f"unsupported placeholder {{{var}}}")
