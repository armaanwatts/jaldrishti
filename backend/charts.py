import altair as alt
import pandas as pd

def history_chart(rows, single, tr):
    import streamlit as st
    values=rows.dropna(subset=['depth']).copy()
    if values.empty: st.info(tr('no_records'));return
    if single:
        values['round']=values.date.dt.to_period('M').dt.to_timestamp()
        chart=values.groupby('round',as_index=False).agg(depth=('depth','median'),count=('depth','size'))
    else:
        values['round']=values.date.dt.to_period('M').dt.to_timestamp()
        # Each station contributes once per calendar month; avoid overweighting repeated readings.
        monthly=values.groupby(['station_key','round'],as_index=False).depth.median()
        chart=monthly.groupby('round',as_index=False).agg(depth=('depth','median'),low=('depth',lambda v:v.quantile(.25)),high=('depth',lambda v:v.quantile(.75)),count=('station_key','nunique'))
        band=alt.Chart(chart).mark_area(opacity=.18,color='#147b82').encode(x=alt.X('round:T',title=tr('date')),y=alt.Y('low:Q',scale=alt.Scale(reverse=True,zero=False),title=tr('depth')),y2='high:Q')
        st.caption(tr('district_graph_note'))
    base=alt.Chart(chart).encode(x=alt.X('round:T',title=tr('date')),y=alt.Y('depth:Q',title=tr('depth'),scale=alt.Scale(reverse=True,zero=False)),tooltip=[alt.Tooltip('round:T',title=tr('date'),format='%Y-%m'),alt.Tooltip('depth:Q',title=tr('depth'),format='.2f'),alt.Tooltip('count:Q',title=tr('readings' if single else 'count'))])
    line=base.mark_line(point=True,color='#147b82')
    st.altair_chart((line if single else band+line).properties(height=340).interactive(),width="stretch")
    st.caption(tr('graph_note'))
    if len(chart)>1:
        st.altair_chart(alt.Chart(chart).mark_bar(color='#91b8be').encode(x=alt.X('round:T',title=tr('date')),y=alt.Y('count:Q',title=tr('count'))).properties(height=100),width="stretch")
    st.download_button(tr('graph_download'),chart.to_csv(index=False),'groundwater_history.csv','text/csv')
