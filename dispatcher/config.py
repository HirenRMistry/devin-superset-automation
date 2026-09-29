import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    devin_api_key: str
    devin_org_id: str
    devin_base_url: str
    github_token: str
    target_repo: str
    dispatch_label: str
    webhook_secret: str
    simulate: bool
    auto_nudge: bool
    poll_interval_s: int
    max_acu_limit: int | None
    db_path: str


def load() -> Config:
    return Config(
        devin_api_key=os.environ.get("DEVIN_API_KEY", ""),
        devin_org_id=os.environ.get("DEVIN_ORG_ID", ""),
        devin_base_url=os.environ.get("DEVIN_BASE_URL", "https://api.devin.ai"),
        github_token=os.environ.get("GH_TOKEN", ""),
        target_repo=os.environ.get("TARGET_REPO", "HirenRMistry/superset"),
        dispatch_label=os.environ.get("DISPATCH_LABEL", "devin-fix"),
        webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
        simulate=os.environ.get("SIMULATE", "").lower() in {"1", "true", "yes"},
        auto_nudge=os.environ.get("AUTO_NUDGE", "").lower() in {"1", "true", "yes"},
        poll_interval_s=int(os.environ.get("POLL_INTERVAL_S", "60")),
        max_acu_limit=(int(v) if (v := os.environ.get("MAX_ACU_LIMIT")) else None),
        db_path=os.environ.get("DB_PATH", "/data/runs.db" if os.path.isdir("/data") else "runs.db"),
    )
