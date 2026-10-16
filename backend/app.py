from pathlib import Path
import hashlib
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import (load_records, latest_stations, current_status, summary_facts, retrieve,
                  local_answer, status_message, VIDARBHA, MARATHWADA, RESOURCE, MODEL)
from i18n import t, district_name, block_name
from map_view import map_payload, render_map
from charts import history_chart
from admin import panel

ROOT = Path(__file__).parent
st.set_page_config(page_title="JalDrishti", page_icon="💧", layout="wide")
st.markdown("<style>.block-container{padding-top:2rem;max-width:1400px}div[data-testid='stMetric']{background:#147b8210;padding:12px;border-radius:12px}</style>", unsafe_allow_html=True)

@st.cache_data
def records(version):
    return load_records()

@st.cache_data
def geography():
    return {key:json.loads((ROOT / "data" / filename).read_text()) for key, filename in {
        "states":"india_states.geojson", "districts":"districts.geojson", "blocks":"blocks.geojson"
    }.items()}

df = records((ROOT / "data/observations.csv").stat().st_mtime_ns)
geo = geography()
language = st.sidebar.selectbox("Language / भाषा", ["English", "Hindi", "Marathi"], format_func=lambda v:{"English":"English", "Hindi":"हिन्दी", "Marathi":"मराठी"}[v], key="ui_language")
tr = lambda key: t(key, language)
st.title(tr("title"))
st.caption(tr("tagline"))

def reset_area():
    st.session_state["selected_block"] = "__all__"
    st.session_state["selected_well"] = "__district__"
    st.session_state["map_view"] = "district"

def reset_region():
    reset_area()
    region = st.session_state["selected_region"]
    choices = sorted(df.district.unique())
    if region == "vidarbha": choices = [x for x in choices if x in VIDARBHA]
    elif region == "marathwada": choices = [x for x in choices if x in MARATHWADA]
    st.session_state["selected_district"] = "Yavatmal" if "Yavatmal" in choices else choices[0]

def reset_block():
    st.session_state["selected_well"] = "__district__"
    st.session_state["map_view"] = "district"

def focus_well():
    st.session_state["map_view"] = "well" if st.session_state["selected_well"] != "__district__" else "district"

region = st.sidebar.selectbox(tr("region"), ["all_state", "vidarbha", "marathwada"], format_func=tr, key="selected_region", on_change=reset_region)
districts = sorted(df.district.unique())
if region == "vidarbha": districts = [x for x in districts if x in VIDARBHA]
elif region == "marathwada": districts = [x for x in districts if x in MARATHWADA]
if "selected_district" not in st.session_state or st.session_state["selected_district"] not in districts:
    st.session_state["selected_district"] = "Yavatmal" if "Yavatmal" in districts else districts[0]
district = st.sidebar.selectbox(tr("district"), districts, format_func=lambda v:district_name(v, language), key="selected_district", on_change=reset_area)
district_rows = df[df.district.eq(district)]
block_choices = ["__all__"] + sorted(district_rows.source_tehsil.dropna().unique())
block = st.sidebar.selectbox(tr("block"), block_choices, format_func=lambda v:tr("all_blocks") if v == "__all__" else block_name(v, language), key="selected_block", on_change=reset_block)
area = district_rows if block == "__all__" else district_rows[district_rows.source_tehsil.eq(block)]
stations = latest_stations(area).sort_values("station")
names = stations.set_index("station_key").station.to_dict()
station_key = st.sidebar.selectbox(tr("well"), ["__district__"] + list(names), format_func=lambda v:tr("all_wells") if v == "__district__" else names[v], key="selected_well", on_change=focus_well)
selected_key = None if station_key == "__district__" else station_key
selected = area if selected_key is None else area[area.station_key.eq(selected_key)]

st.warning(tr("old_data"))
c1,c2,c3 = st.columns(3)
c1.metric(tr("count"), selected.station_key.nunique())
c2.metric(tr("readings"), len(selected))
c3.metric(tr("latest"), selected.date.max().strftime("%Y-%m-%d") if len(selected) else "—")

st.subheader(tr("map"))
view = st.radio(tr("map_view"), ["state", "district", "well", "india"], horizontal=True, format_func=lambda v:tr({"state":"state_view", "district":"district_view", "well":"well_view", "india":"india_view"}[v]), key="map_view")
payload = map_payload(df, geo, district, selected_key, language, view, block)
map_html = render_map(payload)
if hasattr(st, "iframe"):
    st.iframe(map_html, height=660, alt=tr("map"))
else:
    components.html(map_html, height=660, scrolling=False)
st.caption(tr("boundary_note"))
st.caption(tr("source_names"))

def facts_table(facts):
    if not facts:
        return
    table = []
    for f in facts:
        table.append({tr("district"):district_name(f["label"], language), tr("well"):f.get("station", "—"), tr("count"):f["station_count"], tr("readings"):f["measurement_count"], tr("date"):f['first_date'] + " → " + f['last_date'], tr("source"):f['id'] + " · CGWB / NWDP"})
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")

def show_local_answer(question, facts, cache_key):
    if cache_key not in st.session_state:
        with st.spinner(tr("loading")):
            st.session_state[cache_key] = local_answer(question, facts, language)
    result = st.session_state[cache_key]
    st.info(result["answer"])
    st.caption(tr("ai_draft"))
    source_lookup = {f["id"]: f["source"] for f in facts}
    st.markdown(" · ".join(f"[{ref} · CGWB]({source_lookup[ref]})" for ref in result["sources"]))

historical,current,future,questions,sources,admin_tab = st.tabs([tr(k) for k in ["historical", "current", "future", "questions", "source_info", "admin"]])
with historical:
    st.subheader(tr("graph_title"))
    history_chart(selected, selected_key is not None, tr)
    if selected_key and not selected.empty:
        values = selected.dropna(subset=["depth"]).sort_values("date")
        if not values.empty:
            last = values.iloc[-1]
            st.subheader(names[selected_key])
            st.metric(tr("depth"), f"{last.depth:g}")
            st.caption(tr("unit") + " · " + last.date.strftime("%Y-%m-%d"))
            if len(values) >= 2:
                change = round(float(last.depth - values.iloc[0].depth), 2)
                st.write(tr("closer" if change < 0 else ("deeper" if change > 0 else "same")).format(amount=f"{abs(change):g}"))
                st.caption(tr("no_trend"))
            chart = values[["date", "depth"]].rename(columns={"date":tr("date"), "depth":tr("depth")}).set_index(tr("date"))
            # The shared graph above includes the selected well.
    else:
        st.write(tr("select_well"))
    display = selected[["station", "source_tehsil", "date", "depth"]].tail(60).rename(columns={"station":tr("well"), "source_tehsil":tr("source_block"), "date":tr("date"), "depth":tr("depth")})
    st.dataframe(display, hide_index=True, width="stretch")
    facts = [summary_facts(selected, district)] if len(selected) else []
    signature = hashlib.sha256((district+str(selected_key)+str(block)+language+str((ROOT / "data/observations.csv").stat().st_mtime_ns)).encode()).hexdigest()[:16]
    summary_key = "summary_" + signature
    if st.button(tr("summary"), key="summary_button"):
        try:
            show_local_answer("Explain the selected historical records simply. Describe the last record and explain that current and future conditions are unknown.", facts, summary_key)
        except Exception as error:
            st.warning(tr("unavailable"))
            with st.expander(tr("source_info")): st.code(type(error).__name__ + ": " + str(error))
    elif summary_key in st.session_state:
        st.info(st.session_state[summary_key]["answer"])
        st.caption(tr("ai_draft"))
    st.download_button(tr("download"), selected.to_csv(index=False).encode("utf-8"), "jaldrishti_selected.csv", "text/csv")

with current:
    freshness = current_status(selected)
    st.subheader(tr("current"))
    if freshness["supported"]:
        st.info(tr("recent_not_now"))
    else:
        st.warning(tr("no_current"))
    if freshness["latest_date"]:
        st.write(tr("latest") + ": " + freshness["latest_date"])
    st.caption(tr("no_trend"))

with future:
    st.subheader(tr("future"))
    st.warning(tr("no_future"))
    evaluation = ROOT / "outputs/evaluation.json"
    if evaluation.exists():
        with st.expander(tr("backtest")):
            report = json.loads(evaluation.read_text())
            st.dataframe(pd.DataFrame(report["results"]).rename(columns={"split":tr("evaluation_split"),"evaluated":tr("readings"),"baseline_mae_m":tr("baseline_error"),"model_mae_m":tr("model_error")}), hide_index=True)
            st.caption(tr("backtest_note"))
    if selected_key and len(selected.dropna(subset=["depth"])):
        with st.expander(tr("scenario")):
            shift = st.slider(tr("scenario_shift"), min_value=-5.0, max_value=5.0, value=0.0, step=0.25)
            last = selected.dropna(subset=["depth"]).sort_values("date").iloc[-1]
            st.metric(tr("scenario"), f"{float(last.depth)+shift:.2f} m")
            st.caption(tr("scenario_note") + " · " + last.date.strftime("%Y-%m-%d"))
            if float(last.depth)+shift < 0: st.info(tr("above_ground"))

with questions:
    st.subheader(tr("questions"))
    st.caption(tr("coverage"))
    st.caption(tr("rag_note"))
    if st.button(tr("clear_chat")):
        st.session_state["question_history"] = []
    scope = st.radio(tr("scope"), ["district", "well"], format_func=lambda v:tr("scope_"+v), horizontal=True)
    with st.form("district_question"):
        question = st.text_input(tr("questions"), placeholder=tr("question_hint"), max_chars=1200)
        ask = st.form_submit_button(tr("ask"))
    st.session_state.setdefault("question_history", [])
    if ask and question.strip():
        result = retrieve(df, question, district, selected_key if scope == "well" else None)
        entry = {"question":question, "language":language, "districts":result["districts"], "facts":result["facts"]}
        if scope == "well" and selected_key is None and result["districts"] == [district]:
            entry["answer"] = tr("select_well")
        elif result["status"] != "ok" or not result["facts"]:
            entry["answer"] = status_message(result["status"], language)
        else:
            try:
                with st.spinner(tr("loading")):
                    reply = local_answer(question, result["facts"], language)
                entry.update(reply)
                entry["generated"] = True
            except Exception:
                entry["answer"] = tr("unavailable")
        st.session_state["question_history"].append(entry)
    for entry in reversed(st.session_state["question_history"][-8:]):
        if entry["language"] != language:
            continue
        st.markdown("**" + entry["question"].replace("<", "&lt;") + "**")
        st.write(entry["answer"])
        if entry.get("generated"):
            st.caption(tr("ai_draft"))
        st.caption(tr("retrieved") + ": " + ", ".join(district_name(d, language) for d in entry["districts"]))
        with st.expander(tr("evidence")):
            facts_table(entry["facts"])
            for fact in entry["facts"]:
                st.markdown(f"[{fact['id']} · CGWB]({fact['source']})")
                for link in fact.get("source_urls", "").split(" | "):
                    if link: st.markdown(f"[CGWB / NWDP]({link})")
            st.download_button(tr("evidence_download"), json.dumps(entry["facts"], ensure_ascii=False, indent=2), "retrieved_evidence.json", "application/json", key="evidence_"+str(id(entry)))
        st.divider()

with sources:
    st.write(tr("report_separate"))
    st.write(tr("numbers"))
    st.markdown(f"[CGWB / NWDP]({RESOURCE})")
    st.caption(tr("boundary_note"))
    st.write("geoBoundaries · ADM2 / ADM3: ODbL 1.0 · ADM1: CC BY 2.5 IN · Leaflet: BSD-2-Clause")
    st.caption(MODEL + " · Ollama · 127.0.0.1")
    with st.expander(tr("source_info")):
        st.json(json.loads((ROOT / "data/sources.json").read_text()))
        st.json(json.loads((ROOT / "data/history_manifest.json").read_text()))

with admin_tab:
    panel(df, tr)
