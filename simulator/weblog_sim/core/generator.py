from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Tuple, Optional

from .timeutil import apache_time, KST
from .randomutil import clamp, poisson, make_uuid, weighted_choice
from .scenario import ScenarioConfig, PageSpec
from .traffic import WeatherDrift, traffic_multiplier, apply_source_volume, should_drop_source_event
from .http_model import sample_latency_ms, sample_status, sample_bytes, sample_referrer, event_to_path, apply_source_http_effects
from .identity import IdentityPool
from .weather_provider import build_weather_provider
from .exogenous import ExogenousState
from .source_contract import SourceCookieContext, build_source_cookie_kv
from ..meta.store_base import MetaStore, LogFormatMeta


@dataclass
class Session:
    sid: str
    visitor_pcid: str
    start: datetime
    end: datetime
    is_new_visitor: bool = False
    target_pageviews: int = 1
    emitted_pageviews: int = 0
    burst_mode: bool = False


class WeblogGenerator:
    """
    Pre-ML reliability oriented generator.

    The original generator mostly sampled a page + generic event and then delegated
    final path rendering to event_to_path(page.path, event). That made it easy to
    produce broad activity, but it did not reliably emit funnel completion URLs such as:
      /auth/success.do
      /card/submit.do
      /loan/submit.do
      /transfer/confirm.do

    This version keeps the public interface the same but adds explicit funnel-aware
    path generation so downstream metric_value_day can observe completion metrics.
    """

    def __init__(self, scenario: ScenarioConfig, meta_store: MetaStore, drift: WeatherDrift, seed: Optional[int] = None):
        self.scenario = scenario
        self.meta_store = meta_store
        self.drift = drift
        if seed is not None:
            random.seed(seed)
        self.id_pool = IdentityPool(scenario, drift)
        self.new_visit_ratio_by_hh = getattr(
            scenario,
            "new_visit_ratio_by_hh",
            [max(0.05, 1.0 - float(getattr(scenario, "revisit_ratio_daily", 0.70)))] * 24,
        )
        self.revisit_ratio_by_hh = getattr(
            scenario,
            "revisit_ratio_by_hh",
            [float(getattr(scenario, "revisit_ratio_daily", 0.70))] * 24,
        )
        self.session_event_rate_by_hh = getattr(
            scenario,
            "session_event_rate_by_hh",
            [float(getattr(scenario, "session_event_rate", 0.02))] * 24,
        )
        self.weather_provider = build_weather_provider(getattr(scenario, "exogenous", None))

    def _exo(self, when: datetime) -> ExogenousState:
        return self.weather_provider.get_state(when)

    def _weighted_page_items(self, when: datetime) -> List[Tuple[PageSpec, float]]:
        exo = self._exo(when)
        items: List[Tuple[PageSpec, float]] = []
        for p in self.scenario.pages:
            w = float(p.weight) * self.drift.page_weight_multiplier(p.page_type)
            if exo.enabled and exo.campaign_flag == "loan_promo":
                if p.page_type in ("loan", "loan_main", "loan_apply", "product_loan"):
                    w *= 1.8
                elif p.page_type in ("card", "deposit"):
                    w *= 0.9
            elif exo.enabled and exo.campaign_flag == "card_promo":
                if p.page_type in ("card", "card_main", "card_apply", "product_card"):
                    w *= 1.8
                elif p.page_type in ("loan", "deposit"):
                    w *= 0.9
            elif exo.enabled and exo.campaign_flag == "deposit_promo":
                if p.page_type in ("deposit", "deposit_main", "deposit_apply"):
                    w *= 1.6
            if exo.enabled and exo.weather_type == "rain":
                if p.page_type in ("branch", "branch_find", "offline", "visit_reserve"):
                    w *= 0.75
                elif p.page_type in ("main", "dashboard", "account", "loan", "card", "deposit", "home"):
                    w *= 1.05
            items.append((p, max(0.0001, w)))
        return items

    def pick_page(self, when: datetime) -> PageSpec:
        return weighted_choice(self._weighted_page_items(when))

    def pick_event(self, page_type: str, when: datetime) -> str:
        exo = self._exo(when)
        base_mix = self.scenario.event_mix_by_page_type.get(page_type, self.scenario.event_mix_default)
        mix = self.drift.event_mix_override(page_type, base_mix)
        if exo.enabled and exo.campaign_flag in ("loan_promo", "card_promo", "deposit_promo"):
            boosted = []
            for evt, w in mix:
                if evt == "click":
                    boosted.append((evt, w * 1.15))
                elif evt == "view":
                    boosted.append((evt, w * 0.95))
                else:
                    boosted.append((evt, w))
            mix = boosted
        return weighted_choice(mix)

    def _sample_session_length(self) -> int:
        mean = max(30, int(self.scenario.session_mean_sec))
        x = random.expovariate(1.0 / mean)
        return int(clamp(x, 20, 60 * 30))

    def _should_create_new_visitor(self, now_dt: datetime) -> bool:
        hh = now_dt.hour
        exo = self._exo(now_dt)
        new_ratio = float(self.new_visit_ratio_by_hh[hh])
        if exo.enabled and exo.weather_type == "rain" and 18 <= hh <= 22:
            new_ratio *= 0.90
        new_ratio = clamp(new_ratio, 0.02, 0.95)
        if not getattr(self.id_pool, "_visitors", []):
            return True
        return random.random() < new_ratio

    def _create_new_visitor(self, now_dt: datetime):
        if hasattr(self.id_pool, "_create_new_visitor"):
            return self.id_pool._create_new_visitor(now_dt)
        return self.id_pool.get_or_create_visitor(now_dt)

    def _reuse_visitor(self, now_dt: datetime):
        visitors = getattr(self.id_pool, "_visitors", [])
        if not visitors:
            return self._create_new_visitor(now_dt)
        v = random.choice(visitors)
        if hasattr(self.id_pool, "_reuse_visitor"):
            return self.id_pool._reuse_visitor(v, now_dt)
        if hasattr(self.id_pool, "_random_ip_for_country"):
            v.ip = self.id_pool._random_ip_for_country(v.country)
        v.last_seen = now_dt
        v.sessions += 1
        if hasattr(self.id_pool, "maybe_acquire_uid_on_session_start"):
            self.id_pool.maybe_acquire_uid_on_session_start(v, now_dt)
        return v

    def _create_new_or_reuse_visitor(self, now_dt: datetime, force_returning: bool = False):
        visitors = getattr(self.id_pool, "_visitors", [])
        if force_returning and visitors:
            return self._reuse_visitor(now_dt)
        if self._should_create_new_visitor(now_dt):
            return self._create_new_visitor(now_dt)
        return self._reuse_visitor(now_dt)

    def _get_visitor_by_pcid(self, pcid: str):
        for v in getattr(self.id_pool, "_visitors", []):
            if v.pcid == pcid:
                return v
        raise KeyError(f"visitor not found: {pcid}")

    def _funnel_path_and_event(self, page: PageSpec, when: datetime, generic_event: str) -> Tuple[str, str]:
        """
        Return an explicit path/event for key financial funnels.
        Fallback to event_to_path for everything else.
        """
        page_path = (page.path or "").lower()
        page_type = (page.page_type or "").lower()

        def choose(items):
            return weighted_choice(items)

        # auth funnel
        if page_path.startswith("/auth/") or page_type in ("auth", "login", "otp"):
            success_mult = self._completion_multiplier(when, "auth")
            # Keep attempts/otp common, success present but environment-sensitive.
            path = choose([
                ("/auth/login.do", 0.42),
                ("/auth/otp.do", 0.38),
                ("/auth/success.do", 0.20 * success_mult),
            ])
            event = "conversion" if path.endswith("/success.do") else ("click" if path.endswith("/otp.do") else "view")
            return path, event

        # card funnel
        if page_path.startswith("/card/") or page_type in ("card", "card_main", "card_apply", "product_card"):
            submit_mult = self._completion_multiplier(when, "card")
            path = choose([
                ("/card/product.do", 0.34),
                ("/card/usage.do", 0.28),
                ("/card/apply.do", 0.26),
                ("/card/submit.do", 0.12 * submit_mult),
            ])
            if path.endswith("/submit.do"):
                event = "conversion"
            elif path.endswith("/apply.do"):
                event = "click"
            else:
                event = "view"
            return path, event

        # loan funnel
        if page_path.startswith("/loan/") or page_type in ("loan", "loan_main", "loan_apply", "product_loan"):
            submit_mult = self._completion_multiplier(when, "loan")
            path = choose([
                ("/loan/product.do", 0.34),
                ("/loan/status.do", 0.24),
                ("/loan/apply.do", 0.28),
                ("/loan/submit.do", 0.14 * submit_mult),
            ])
            if path.endswith("/submit.do"):
                event = "conversion"
            elif path.endswith("/apply.do"):
                event = "click"
            else:
                event = "view"
            return path, event

        # transfer funnel
        if page_path.startswith("/transfer/") or page_type in ("transfer", "transfer_main", "transfer_apply"):
            confirm_mult = self._completion_multiplier(when, "transfer")
            path = choose([
                ("/transfer/step1.do", 0.72),
                ("/transfer/confirm.do", 0.28 * confirm_mult),
            ])
            event = "conversion" if path.endswith("/confirm.do") else "click"
            return path, event

        # Keep useful concrete paths for common non-funnel sections.
        if page_path.startswith("/account/") or page_type in ("account", "account_main"):
            path = choose([
                ("/account/overview.do", 0.62),
                ("/account/transaction.do", 0.38),
            ])
            return path, "view"

        if page_path.startswith("/customer/") or page_type in ("customer", "notice", "support"):
            return "/customer/notice.do", "view"

        if page_path.startswith("/branch/") or page_type in ("branch", "branch_find"):
            return "/branch/find.do", "view"

        if page_path.startswith("/dashboard") or page_type in ("dashboard",):
            return "/dashboard.do", "view"

        if page_path.startswith("/main") or page_type in ("main", "home"):
            return "/main.do", "view"

        # fallback
        return event_to_path(page.path, generic_event), generic_event

    def _render_line(self, dt: datetime, sess: Session, site_key: str) -> str:
        meta: LogFormatMeta = self.meta_store.get(site_key)
        exo = self._exo(dt)
        page = self.pick_page(dt)
        generic_event = self.pick_event(page.page_type, dt)
        path, event = self._funnel_path_and_event(page, dt, generic_event)
        v = self._get_visitor_by_pcid(sess.visitor_pcid)
        if hasattr(self.id_pool, "maybe_acquire_uid_in_session"):
            self.id_pool.maybe_acquire_uid_in_session(v, dt, event=event, page_type=page.page_type)
        legacy_drift_enabled = self.drift.enabled and self.drift.weather != "none"
        latency = sample_latency_ms(event, page.page_type, drift_enabled=legacy_drift_enabled)
        status = sample_status(latency)
        latency, status = self._apply_exogenous_latency_status(page.page_type, event, dt, latency, status)
        bytes_ = sample_bytes(event, page.page_type)
        ref = sample_referrer(self.scenario.site_host, self.drift.weather, legacy_drift_enabled)
        if event == "view":
            sess.emitted_pageviews += 1
        uid_val = v.uid or ""
        cookie_pcid = v.pcid
        cookie_sid = sess.sid
        cookie_uid = uid_val
        if getattr(exo, "identity_flag", "normal") == "drift":
            # Deterministic identity drift: only the emitted source identifiers are
            # perturbed. Session lookup remains based on the internal visitor object.
            suffix = str(abs(hash((v.pcid, sess.sid, int(dt.timestamp())))) % 100000)
            cookie_pcid = f"{v.pcid}_drift_{suffix}"
            cookie_sid = f"{sess.sid}_drift_{suffix}"
            cookie_uid = f"{uid_val or 'anonymous'}_drift_{suffix}"

        # v0.4/v0.5-ready Source Anomaly Contract.
        # The generator directly emits anomaly cookie fields. No source-file rewrite
        # is used in the normal pipeline path. Do not emit legacy `weather=` alias.
        product_type = "none"
        if "loan" in page.page_type:
            product_type = "loan"
        elif "card" in page.page_type:
            product_type = "card"
        elif "deposit" in page.page_type:
            product_type = "deposit"
        elif "transfer" in page.page_type:
            product_type = "transfer"

        ctx = SourceCookieContext(
            scenario_id=os.getenv("SOURCE_SCENARIO_ID", getattr(self.scenario, "scenario_id", getattr(self.scenario, "scenario_name", "baseline"))) or "baseline",
            scenario_name=os.getenv("SOURCE_SCENARIO_NAME", getattr(self.scenario, "scenario_name", getattr(self.scenario, "scenario_id", "baseline"))) or "baseline",
            domain=product_type if product_type != "none" else "web",
            source_layer="behavior",
            experiment_id=os.getenv("SOURCE_EXPERIMENT_ID", getattr(self.scenario, "experiment_id", "none")) or "none",
            run_id=str(os.getenv("SOURCE_RUN_ID", getattr(self.scenario, "run_id", "none")) or "none"),
        )
        kv = build_source_cookie_kv(
            base_fields={
                "cc": v.country,
                "al": v.accept_lang,
                "device": v.device,
                "pcid": cookie_pcid,
                "sid": cookie_sid,
                "uid": cookie_uid,
                "evt": event,
                "event_type": event,
                "page_type": page.page_type,
                "product_type": product_type,
                "latency_ms": latency,
                "http_status": status,
            },
            exo_state=exo,
            context=ctx,
        )
        ts = apache_time(dt.astimezone(meta.tz))
        return meta.template.format(
            ip=v.ip,
            ts=ts,
            method="GET",
            path=path,
            httpv=meta.http_version,
            status=status,
            bytes=bytes_,
            ref=ref,
            ua=v.ua,
            kv=kv,
        )



    def _sample_target_pageviews(self, when: Optional[datetime] = None) -> int:
        mean = float(self.scenario.target_pv_per_visit_mean)
        std = float(self.scenario.target_pv_per_visit_std)
        cap = int(self.scenario.max_pageviews_per_session)
        if when is not None:
            exo = self._exo(when)
            if exo.enabled:
                mean = max(1.0, mean * float(getattr(exo, "volume_multiplier", 1.0) or 1.0))
        x = int(round(random.gauss(mean, std)))
        return max(1, min(x, cap))

    def _make_session(self, now_dt: datetime, force_returning: bool = False, burst_mode: bool = False) -> Session:
        before_cnt = len(getattr(self.id_pool, "_visitors", []))
        v = self._create_new_or_reuse_visitor(now_dt, force_returning=force_returning)
        after_cnt = len(getattr(self.id_pool, "_visitors", []))
        is_new_visitor = after_cnt > before_cnt
        sid = make_uuid()
        length_sec = self._sample_session_length()
        target_pv = self._sample_target_pageviews(now_dt)
        return Session(
            sid=sid,
            visitor_pcid=v.pcid,
            start=now_dt,
            end=now_dt + timedelta(seconds=length_sec),
            is_new_visitor=is_new_visitor,
            target_pageviews=target_pv,
            emitted_pageviews=0,
            burst_mode=burst_mode,
        )

    def _apply_exogenous_latency_status(
        self,
        page_type: str,
        event: str,
        when: datetime,
        latency: int,
        status: int,
    ) -> Tuple[int, int]:
        exo = self._exo(when)
        if exo.enabled:
            latency, status = apply_source_http_effects(latency, status, exo)
            if exo.system_flag == "auth_delay" and page_type in ("login", "auth", "otp"):
                if random.random() < 0.05:
                    status = random.choice([401, 429, 500, 503])
        return latency, status

    def _completion_multiplier(self, when: datetime, domain: str) -> float:
        exo = self._exo(when)
        mult = 1.0
        if exo.enabled:
            mult *= float(getattr(exo, "conversion_multiplier", 1.0) or 1.0)
            if exo.system_flag == "auth_delay" and domain == "auth":
                mult *= 0.45
            if exo.system_flag == "degraded":
                mult *= 0.75
            if exo.weather_type == "rain" and domain in ("loan", "card", "transfer"):
                mult *= 0.9
        return max(0.05, min(mult, 1.5))

    def _session_event_rate(self, dt: datetime) -> float:
        exo = self._exo(dt)
        base_rate = float(self.session_event_rate_by_hh[dt.hour])
        if exo.enabled:
            base_rate *= float(getattr(exo, "volume_multiplier", 1.0) or 1.0)
            if exo.weather_type == "rain" and 18 <= dt.hour <= 22:
                base_rate *= 1.05
            if exo.system_flag == "auth_delay":
                base_rate *= 0.96
        return max(0.0, base_rate)


    # v0.4 no_data explicit source marker
    def _render_no_data_marker_line(self, dt: datetime, site_key: str) -> str:
        """Render an explicit source-level no_data marker line.

        When suppress_input=1, normal events are intentionally dropped, so there
        may be no user event to carry drift=on / affected=1 / anomaly_type=no_data.
        This marker is generated by simulator core, not by source-file rewrite,
        and lets downstream validation distinguish "true source collapse" from
        "no anomaly metadata".
        """
        import os

        meta: LogFormatMeta = self.meta_store.get(site_key)
        exo = self._exo(dt)
        scenario_id = os.environ.get("SOURCE_SCENARIO_ID", "source_no_data")
        run_id = os.environ.get("SOURCE_RUN_ID", "")
        experiment_id = os.environ.get("EXPERIMENT_ID", "")
        exo_state_id = f"exo_{dt.strftime('%Y%m%d_%H')}"
        contract_id = f"contract_{scenario_id}"

        kv = (
            f"cc=NA; al=na; device=system; "
            f"pcid=no_data_marker; sid=no_data_{dt.strftime('%Y%m%d%H%M')}; uid=; "
            f"evt=source_no_data_marker; page_type=source_control; "
            f"latency_ms=0; http_status=204; "
            f"schema_version={getattr(exo, 'schema_version', 'v0.4-source-anomaly-contract')}; "
            f"scenario_id={scenario_id}; scenario_name={scenario_id}; "
            f"domain=web; source_layer=behavior; anomaly_type=no_data; "
            f"drift=on; affected=1; exo_state_id={exo_state_id}; "
            f"anomaly_contract_id={contract_id}; experiment_id={experiment_id}; run_id={run_id}; "
            f"weather_type={getattr(exo, 'weather_type', 'clear')}; "
            f"campaign_flag={getattr(exo, 'campaign_flag', 'none')}; "
            f"system_flag={getattr(exo, 'system_flag', 'normal')}; "
            f"volume_multiplier={getattr(exo, 'volume_multiplier', 1.0)}; "
            f"conversion_multiplier={getattr(exo, 'conversion_multiplier', 1.0)}; "
            f"latency_shift_ms={getattr(exo, 'latency_shift_ms', 0)}; "
            f"drop_probability={getattr(exo, 'drop_probability', 0.0)}; "
            f"timeout_multiplier={getattr(exo, 'timeout_multiplier', 1.0)}; "
            f"retry_multiplier={getattr(exo, 'retry_multiplier', 1.0)}; "
            f"duplicate_multiplier={getattr(exo, 'duplicate_multiplier', 1.0)}; "
            f"event_time_skew_ms={getattr(exo, 'event_time_skew_ms', 0)}; "
            f"suppress_input=1; "
            f"schema_flag={getattr(exo, 'schema_flag', 'normal')}; "
            f"identity_flag={getattr(exo, 'identity_flag', 'normal')}; "
            f"pcid_stability={getattr(exo, 'pcid_stability', 'stable')}; "
            f"session_stability={getattr(exo, 'session_stability', 'stable')}; "
            f"customer_id_stability={getattr(exo, 'customer_id_stability', 'stable')}; "
            f"traffic_actor=system; bot_flag=0; user_agent_flag=marker; ip_concentration_flag=normal; "
            f"recovery_flag=none; backlog_flush=0; transaction_delay_ms=0; event_ingestion_delay_ms=0; "
            f"privacy_flag=normal; pii_detected=0; sensitive_field_flag=none; masking_status=not_applicable; "
            f"financial_product=none; funnel_stage=none; state_transition=none; "
            f"expected_state=none; actual_state=none; reconciliation_flag=source_no_data_marker; "
            f"exo_source=exogenous_timeline_v1;"
        )
        ts = apache_time(dt.astimezone(meta.tz))
        return meta.template.format(
            ip="0.0.0.0",
            ts=ts,
            method="GET",
            path="/__source_anomaly__/no_data_marker.do",
            httpv=meta.http_version,
            status=204,
            bytes=0,
            ref="-",
            ua="source-no-data-marker/1.0",
            kv=kv,
        )

    def generate(self, start_dt: datetime, end_dt: datetime, avg_rps: float, site_key: str) -> Iterable[str]:
        dt = start_dt
        active: List[Session] = []

        while dt <= end_dt:
            exo = self._exo(dt)
            # v0.4 no_data explicit source marker
            # Emit one marker per minute while suppress_input=1. Normal user events
            # are not generated in this window, but the source contract still needs
            # explicit drift/affected/anomaly_type metadata for audit and downstream
            # validation. This is generated inside simulator core, not by rewriting
            # the source file after generation.
            if getattr(exo, "suppress_input", False):
                marker_key = dt.strftime("%Y-%m-%dT%H:%M")
                if not hasattr(self, "_no_data_marker_keys"):
                    self._no_data_marker_keys = set()
                if marker_key not in self._no_data_marker_keys:
                    self._no_data_marker_keys.add(marker_key)
                    yield self._render_no_data_marker_line(dt, site_key=site_key)
                dt += timedelta(seconds=1)
                continue

            mult = traffic_multiplier(dt.astimezone(KST), self.drift)
            rps = apply_source_volume(avg_rps * mult, exo) if exo.enabled else avg_rps * mult
            session_start_rate = clamp(rps / 8.0, 0.0, 20.0)
            new_sessions = poisson(session_start_rate)

            for _ in range(new_sessions):
                jitter_ms = random.randint(0, 999)
                st = dt + timedelta(milliseconds=jitter_ms)
                active.append(self._make_session(st, force_returning=False, burst_mode=False))

            active = [s for s in active if s.end >= dt]
            lines: List[Tuple[datetime, str]] = []

            for s in active:
                n = poisson(self._session_event_rate(dt))
                for _ in range(n):
                    if s.emitted_pageviews >= s.target_pageviews and random.random() < 0.92:
                        continue
                    jitter_ms = random.randint(0, 999)
                    jitter_us = random.randint(0, 999)
                    t = dt + timedelta(milliseconds=jitter_ms, microseconds=jitter_us)
                    if t <= end_dt:
                        event_exo = self._exo(t)
                        if should_drop_source_event(event_exo):
                            continue
                        lines.append((t, self._render_line(t, s, site_key=site_key)))

            lines.sort(key=lambda x: (x[0], x[1]))
            for _, line in lines:
                yield line

            dt += timedelta(seconds=1)

        if hasattr(self.id_pool, "promote_today_to_historical"):
            self.id_pool.promote_today_to_historical()
