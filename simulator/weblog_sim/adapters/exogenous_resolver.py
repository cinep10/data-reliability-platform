from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional
import json, yaml

@dataclass
class ExogenousState:
    enabled: bool
    weather_type: str
    campaign_flag: str
    system_flag: str
    volume_multiplier: float
    conversion_multiplier: float
    timeout_multiplier: float
    retry_multiplier: float

@dataclass
class ResolvedExogenous:
    mode: str
    source: str
    as_of_ts: Optional[str]
    state: ExogenousState
    raw_payload: dict[str, Any]

    def to_snapshot_record(self) -> dict[str, Any]:
        return {
            'enabled': 1 if self.state.enabled else 0,
            'weather_type': self.state.weather_type,
            'campaign_flag': self.state.campaign_flag,
            'system_flag': self.state.system_flag,
            'volume_multiplier': self.state.volume_multiplier,
            'conversion_multiplier': self.state.conversion_multiplier,
            'timeout_multiplier': self.state.timeout_multiplier,
            'retry_multiplier': self.state.retry_multiplier,
            'source': self.source,
            'as_of_ts': self.as_of_ts,
            'raw_payload_json': json.dumps(self.raw_payload, ensure_ascii=False),
        }

def resolve_exogenous_state(exogenous_config_path: Optional[Path], profile_id: str, target_date: str, scenario_name: str, scenario_mode: str) -> ResolvedExogenous:
    if exogenous_config_path is None:
        return ResolvedExogenous('disabled', 'static', None, ExogenousState(False,'clear','none','normal',1.0,1.0,1.0,1.0), {'mode':'disabled'})
    payload = yaml.safe_load(exogenous_config_path.read_text(encoding='utf-8')) or {}
    enabled = bool(payload.get('enabled', False))
    mode = str(payload.get('mode', 'static')) if enabled else 'disabled'
    state = ExogenousState(
        enabled=enabled,
        weather_type=str(payload.get('weather_type', 'clear')),
        campaign_flag=str(payload.get('campaign_flag', 'none')),
        system_flag=str(payload.get('system_flag', 'normal')),
        volume_multiplier=float(payload.get('volume_multiplier', 1.0)),
        conversion_multiplier=float(payload.get('conversion_multiplier', 1.0)),
        timeout_multiplier=float(payload.get('timeout_multiplier', 1.0)),
        retry_multiplier=float(payload.get('retry_multiplier', 1.0)),
    )
    return ResolvedExogenous(mode, str(payload.get('source','static')), payload.get('as_of_ts'), state, {
        'profile_id': profile_id, 'target_date': target_date, 'scenario_name': scenario_name,
        'scenario_mode': scenario_mode, 'config': payload
    })
