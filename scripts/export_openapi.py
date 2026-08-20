#!/usr/bin/env python3
"""Export the DFAT OpenAPI schema to JSON and YAML files."""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "api"


def main() -> None:
    from dfat.app import create_app

    app = create_app()
    schema = app.openapi()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / "openapi.json"
    json_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI JSON exported to {json_path}")

    try:
        import yaml

        yaml_path = OUTPUT_DIR / "openapi.yaml"
        yaml_path.write_text(
            yaml.dump(schema, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"OpenAPI YAML exported to {yaml_path}")
    except ImportError:
        print("PyYAML not installed - skipping YAML export (pip install pyyaml)")


if __name__ == "__main__":
    main()
