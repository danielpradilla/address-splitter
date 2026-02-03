import re

def render_prompt(template: str, *, name: str, country: str, address: str) -> str:
    # Strict, simple templating: only allow the known placeholders.
    # Prevent surprises by leaving unknown {things} untouched.
    rendered = template
    rendered = rendered.replace("{name}", name)
    rendered = rendered.replace("{country}", country)
    rendered = rendered.replace("{address}", address)
    return rendered


def validate_template(template: str) -> None:
    if "{address}" not in template:
        raise ValueError("prompt_template must include {address}")

    # Optional: flag unknown placeholders
    allowed = {"name", "country", "address"}
    for var in re.findall(r"\{([a-zA-Z0-9_]+)\}", template):
        if var not in allowed:
            raise ValueError(f"unsupported placeholder {{{var}}}")
