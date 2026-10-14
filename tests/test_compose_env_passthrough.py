"""The API container has no ``env_file``: ``environment:`` in the compose file is
the *only* channel that puts a variable into it.

Two production settings were silently dead for exactly this reason.
``ADMIN_EMAILS`` was overridden by a hardcoded default inside the compose file, and
``ZENMUX_API_KEY`` was never mentioned at all, so the /api/v1/zenmux routes answered
503 "Zenmux is not configured" no matter what the operator put in
``.env.production``. Both failures were invisible: the service started, reported
healthy, and the value was simply never delivered.

These tests assert the plumbing rather than the behaviour, so the next key added to
``Settings`` cannot fail the same way.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.prod.yml"
EXAMPLE_PATH = ROOT / ".env.production.example"


@pytest.fixture(scope="module")
def api_environment() -> dict[str, str]:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return compose["services"]["api"]["environment"]


#: Settings the product cannot work without, or that silently disable a feature.
#: Each one must be interpolated from the environment in the compose file.
REQUIRED_PASSTHROUGH = (
    "ADMIN_EMAILS",
    "ZENMUX_API_KEY",
    "RECAPTCHA_SECRET_KEY",
    "TURNSTILE_SECRET_KEY",
    "KHPAY_API_KEY",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "DATA_DIR",
)


@pytest.mark.parametrize("name", REQUIRED_PASSTHROUGH)
def test_api_environment_passes_the_setting_through(api_environment, name) -> None:
    """A setting absent from compose can never reach the API, whatever .env says."""
    assert name in api_environment, (
        f"{name} is not in the api service's environment block. The api has no "
        f"env_file, so this compose file is the only way the value reaches it."
    )


@pytest.mark.parametrize("name", REQUIRED_PASSTHROUGH)
def test_the_passthrough_is_interpolated_not_hardcoded(api_environment, name) -> None:
    """A literal value here silently wins over the operator's .env.production."""
    value = str(api_environment[name])
    if value.startswith("${"):
        assert ":-" in value or ":?" in value or value.endswith("}"), (
            f"{name} does not declare a default: {value}"
        )
        return
    # DATA_DIR is a genuine literal (the container mount point), and that is fine.
    assert name == "DATA_DIR", (
        f"{name} is hardcoded to {value!r}; setting it in .env.production would have "
        f"no effect."
    )


def test_admin_emails_has_no_literal_fallback() -> None:
    """The exact bug that left the old administrator in control after a redeploy."""
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    value = str(compose["services"]["api"]["environment"]["ADMIN_EMAILS"])
    assert "menmengleapx1" not in value
    assert "devlopercyberghost" not in value
    assert value == "${ADMIN_EMAILS:-}"


def test_zenmux_base_url_defaults_to_the_project_router(api_environment) -> None:
    assert api_environment["ZENMUX_BASE_URL"] == (
        "${ZENMUX_BASE_URL:-https://router.pkay.fun/v1/agenza}"
    )


def test_no_service_mounts_the_data_volume_except_api() -> None:
    """Only the api holds users.json; a second writer would clobber it."""
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    holders = [
        name
        for name, svc in compose["services"].items()
        if any("pkay_data:/data" in str(v) for v in svc.get("volumes", []) or [])
    ]
    assert holders == ["api"]


def test_redeploy_does_not_prune_volumes() -> None:
    script = (ROOT / "deploy/redeploy.sh").read_text(encoding="utf-8")
    for forbidden in ("down -v", "--volumes", "volume rm", "volume prune"):
        assert forbidden not in script


def test_preflight_runs_inside_a_container_that_has_python() -> None:
    """alpine ships no python3, so parsing users.json there always 'fails'."""
    script = (ROOT / "deploy/preflight-data.sh").read_text(encoding="utf-8")
    assert "docker exec" in script
    # Strip comments: the file explains *why* it avoids alpine, and that prose
    # mentions python3 too.
    code = "\n".join(
        line for line in script.splitlines() if line.strip() and not line.strip().startswith("#")
    )
    assert "python3" not in code, "preflight must not shell out to python3 in a bare alpine container"
    assert "alpine" not in code


# ------------------------------------------------ the example env file

EXAMPLE_ONLY = ("ZENMUX_API_KEY", "RECAPTCHA_SECRET_KEY", "NEXT_PUBLIC_RECAPTCHA_SITE_KEY")


@pytest.mark.parametrize("name", EXAMPLE_ONLY)
def test_the_example_env_file_documents_the_setting(name) -> None:
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert f"{name}=" in text, f"{name} is undocumented in .env.production.example"


def test_zenmux_and_recaptcha_are_documented_together() -> None:
    """Both halves of each pair belong in the same file, or they drift apart."""
    text = EXAMPLE_PATH.read_text(encoding="utf-8")
    assert "ZENMUX_API_KEY" in text and "ZENMUX_BASE_URL" in text
    assert "NEXT_PUBLIC_RECAPTCHA_SITE_KEY" in text and "RECAPTCHA_SECRET_KEY" in text
