#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path

root = Path(os.environ.get('PROJECT_ROOT', os.getcwd()))
path = root / 'pipelines/commerce/visualization/build_case_obs_001_figures.R'
if not path.exists():
    raise SystemExit(f'missing file: {path}')
text = path.read_text()
orig = text

old = '''decision_reliability <- ifelse(risk_score < 0.30, "HIGH", ifelse(risk_score < 0.60, "MEDIUM", "LOW"))
business_impact <- ifelse(num(ra$impact_evidence_score[1] %||% risk$impact_score[1]) < 0.35, "LIMITED", ifelse(num(ra$impact_evidence_score[1] %||% risk$impact_score[1]) < 0.65, "MODERATE", "HIGH"))
recommended_decision <- ifelse(decision_reliability == "HIGH", "Continue KPI monitoring", ifelse(decision_reliability == "MEDIUM", "Annotate KPI before decision", "Pause KPI-based decisions"))'''
new = '''# Business decision interpretation must not be a direct copy of low authority risk.
# For silent distortion, purchase/conversion KPI reliability is low even when the
# operational authority risk score is low. This keeps Authority Risk and Business
# KPI Decision Reliability explicitly separated in the report layer.
business_kpi_distortion_score <- num(ra$business_kpi_distortion_score[1])
traffic_preservation_score <- num(ra$traffic_preservation_score[1])
criticality_evidence_score <- num(ra$criticality_evidence_score[1])
conversion_gap_rate <- num(conversion$gap_rate[1])
pv_gap_rate <- num(pv$gap_rate[1])
if (pattern == "silent_distortion" || business_kpi_distortion_score >= .60 || (criticality_evidence_score >= .60 && conversion_gap_rate >= .50 && pv_gap_rate <= .12)) {
  decision_reliability <- "LOW"
  business_impact <- "HIGH"
  recommended_decision <- "Freeze purchase/conversion KPI decision"
} else if (pattern == "localized_failure" || concentration_evidence_score >= .35) {
  decision_reliability <- "MEDIUM"
  business_impact <- "SEGMENT-LEVEL"
  recommended_decision <- "Audit affected segment before segment KPI decision"
} else if (risk_score < 0.30) {
  decision_reliability <- "HIGH"
  business_impact <- "LIMITED"
  recommended_decision <- "Continue KPI monitoring"
} else if (risk_score < 0.60) {
  decision_reliability <- "MEDIUM"
  business_impact <- "MODERATE"
  recommended_decision <- "Annotate KPI before decision"
} else {
  decision_reliability <- "LOW"
  business_impact <- "HIGH"
  recommended_decision <- "Pause KPI-based decisions"
}'''
if old in text:
    text = text.replace(old, new)
elif 'decision_reliability <- ifelse(risk_score < 0.30' in text and 'Freeze purchase/conversion KPI decision' not in text:
    raise SystemExit('found old decision block but exact replacement failed; inspect manually')

old = '''# 4 Operational: Why this is not critical
flow <- data.frame(step=1:5, label=c(paste0(fmt_pct(current_gap)," gap\nObserved loss"), paste0("Pattern\n",gsub("_"," ",pattern)), paste0("Impact\n",business_impact), paste0("Risk\n",risk_level," / ",sprintf("%.3f",risk_score)), paste0("Decision\n",recommended_decision)), y=.55)
ar <- data.frame(x=1:4+.30,xend=2:5-.30,y=.55,yend=.55)
p <- card("Figure 4. Why This Is Not Critical", "Evidence → Pattern → Risk → Action translated into operational language.") + ggplot2::geom_segment(data=ar, ggplot2::aes(x=x,xend=xend,y=y,yend=yend), arrow=ggplot2::arrow(length=grid::unit(.16,"inches")), linewidth=.75) + ggplot2::geom_label(data=flow, ggplot2::aes(x=step,y=y,label=label), linewidth=.25,size=3.8,lineheight=.95) + ggplot2::xlim(.5,5.5) + ggplot2::ylim(0,1)
save_plot(p,operational_dir,"fig04_why_this_is_not_critical.png","Why This Is Not Critical","operational","pattern_to_decision_story",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))'''
new = '''# 4 Operational: Operational risk vs business KPI impact
fig04_title <- ifelse(pattern == "silent_distortion", "Figure 4. Operational Risk vs Business KPI Reliability", ifelse(decision_reliability == "HIGH", "Figure 4. Why This Is Not Critical", "Figure 4. Why This Decision Needs Attention"))
flow <- data.frame(step=1:5, label=c(paste0(fmt_pct(current_gap)," gap\nObserved evidence"), paste0("Pattern\n",gsub("_"," ",pattern)), paste0("Operational risk\n",risk_level," / ",sprintf("%.3f",risk_score)), paste0("Business KPI\n",business_impact), paste0("Decision\n",recommended_decision)), y=.55)
ar <- data.frame(x=1:4+.30,xend=2:5-.30,y=.55,yend=.55)
p <- card(fig04_title, "Operational authority risk is separated from business KPI reliability.") + ggplot2::geom_segment(data=ar, ggplot2::aes(x=x,xend=xend,y=y,yend=yend), arrow=ggplot2::arrow(length=grid::unit(.16,"inches")), linewidth=.75) + ggplot2::geom_label(data=flow, ggplot2::aes(x=step,y=y,label=label), linewidth=.25,size=3.8,lineheight=.95) + ggplot2::xlim(.5,5.5) + ggplot2::ylim(0,1)
save_plot(p,operational_dir,"fig04_why_this_is_not_critical.png",gsub("^Figure 4[.] ","",fig04_title),"operational","operational_business_risk_split",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))'''
if old in text:
    text = text.replace(old, new)
else:
    text = text.replace('save_plot(p,operational_dir,"fig04_why_this_is_not_critical.png","Why This Is Not Critical","operational","pattern_to_decision_story",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))', 'save_plot(p,operational_dir,"fig04_why_this_is_not_critical.png","Operational Risk vs Business KPI Reliability","operational","operational_business_risk_split",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))')
    text = text.replace('p <- card("Figure 4. Why This Is Not Critical", "Evidence → Pattern → Risk → Action translated into operational language.")', 'fig04_title <- ifelse(pattern == "silent_distortion", "Figure 4. Operational Risk vs Business KPI Reliability", ifelse(decision_reliability == "HIGH", "Figure 4. Why This Is Not Critical", "Figure 4. Why This Decision Needs Attention"))\np <- card(fig04_title, "Operational authority risk is separated from business KPI reliability.")')

text = text.replace('save_plot(p,technical_dir,"fig06_potential_investigation_candidates.png","Potential Investigation Candidates","technical","obs_reference_investigation_candidates",c("v05_obs_app_version_measurement_day","v05_obs_sdk_version_measurement_day"))',
                    'save_plot(p,technical_dir,"fig06_potential_investigation_candidates.png","Root Cause Concentration Analysis","technical","obs_reference_concentration_analysis",c("v05_obs_app_version_measurement_day","v05_obs_sdk_version_measurement_day"))')
text = text.replace('ggplot2::labs(title="Figure 6. Potential Investigation Candidates", subtitle="These observations support investigation only and do not influence risk calculation.", x=NULL, y="Missing rate")',
                    'ggplot2::labs(title="Figure 6. Root Cause Concentration Analysis", subtitle="OBS reference only: candidates support investigation and do not influence risk calculation.", x=NULL, y="Missing rate")')

old = '''risk_parts <- data.frame(component=c("Baseline evidence","Statistical evidence","Propagation evidence","Impact evidence","Pattern confidence","Likelihood","Impact","Risk"), score=c(num(ra$baseline_evidence_score[1] %||% ra$baseline_delta[1]),num(ra$statistical_evidence_group_score[1] %||% ra$statistical_evidence_effective_score[1]),num(ra$propagation_evidence_score[1] %||% ra$cross_domain_propagation_strength[1]),num(ra$impact_evidence_score[1] %||% risk$impact_score[1]),pattern_conf,num(risk$likelihood_score[1]),num(risk$impact_score[1]),risk_score))'''
new = '''risk_parts <- data.frame(component=c("Baseline evidence","Statistical evidence","Propagation evidence","Impact evidence","Concentration evidence","Criticality evidence","Business KPI distortion","Traffic preservation","Pattern confidence","Likelihood","Impact","Risk"), score=c(num(ra$baseline_evidence_score[1] %||% ra$baseline_delta[1]),num(ra$statistical_evidence_group_score[1] %||% ra$statistical_evidence_effective_score[1]),num(ra$propagation_evidence_score[1] %||% ra$cross_domain_propagation_strength[1]),num(ra$impact_evidence_score[1] %||% risk$impact_score[1]),num(ra$concentration_evidence_score[1]),num(ra$criticality_evidence_score[1]),business_kpi_distortion_score,traffic_preservation_score,pattern_conf,num(risk$likelihood_score[1]),num(risk$impact_score[1]),risk_score))'''
if old in text:
    text = text.replace(old, new)

text = text.replace('save_plot(p,technical_dir,"appendix04_pattern_driven_risk_decomposition.png","Pattern-driven Risk Decomposition","technical","pattern_driven_risk_decomposition",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))',
                    'save_plot(p,technical_dir,"appendix04_pattern_driven_risk_decomposition.png","Evidence to Pattern to Risk Decomposition","technical","evidence_pattern_risk_decomposition",c("reliability_analysis_result_day_v05","unified_reliability_score_day_v05"))')
text = text.replace('ggplot2::labs(title="Appendix 4. Pattern-driven Risk Decomposition", subtitle="Evidence does not directly drive risk. Pattern is the risk driver.", x=NULL,y="Score")',
                    'ggplot2::labs(title="Appendix 4. Evidence → Pattern → Risk Decomposition", subtitle="Evidence does not directly drive risk. Pattern is the risk driver; criticality explains purchase/conversion distortion.", x=NULL,y="Score")')

# Add v2 evidence fields to manifest if the old manifest line exists.
old = 'observed_gap_rate=current_gap,decision_reliability=decision_reliability,business_impact=business_impact,recommended_decision=recommended_decision,'
new = 'observed_gap_rate=current_gap,decision_reliability=decision_reliability,business_impact=business_impact,recommended_decision=recommended_decision,business_kpi_distortion_score=business_kpi_distortion_score,traffic_preservation_score=traffic_preservation_score,criticality_evidence_score=criticality_evidence_score,conversion_gap_rate=conversion_gap_rate,pv_gap_rate=pv_gap_rate,'
if old in text:
    text = text.replace(old, new)

if text == orig:
    print('No changes made; file may already be patched.')
else:
    path.write_text(text)
    print(f'[OK] patched {path}')
