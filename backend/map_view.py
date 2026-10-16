"""One map generated from the same district, well and language as the app.

Leaflet JS/CSS are bundled locally. No third-party tile requests are made.
"""
import json
from pathlib import Path
import pandas as pd

from core import canonical, latest_stations, RESOURCE
from i18n import t, district_name, block_name

ROOT = Path(__file__).parent

def map_payload(records, geography, district, station_key, language, view="state", block=None):
    district_features = []
    for f in geography["districts"]["features"]:
        name = canonical(f["properties"]["shapeName"])
        district_features.append({"type": "Feature", "geometry": f["geometry"], "properties": {"district": name, "label": district_name(name, language), "selected": name == district}})
    blocks = []
    for f in geography["blocks"]["features"]:
        if canonical(f["properties"]["district"]) != district:
            continue
        p = f["properties"]
        blocks.append({"type": "Feature", "geometry": f["geometry"], "properties": {"label": block_name(p["shapeName"], language), "lat": p["label_lat"], "lon": p["label_lon"]}})
    current = latest_stations(records[records.district.eq(district)])
    if block and block != "__all__":
        current = current[current.source_tehsil.eq(block)]
    points = []
    for _, r in current.iterrows():
        points.append({"id": r.station_key, "name": str(r.station), "lat": float(r.latitude), "lon": float(r.longitude), "depth": None if pd.isna(r.depth) else float(r.depth), "date": r.date.strftime("%Y-%m-%d"), "block": block_name(str(r.source_tehsil), language), "selected": r.station_key == station_key})
    keys = ["zoom_in", "zoom_out", "selected", "other_districts", "wells", "blocks", "block_labels", "source_block", "depth", "unit", "date", "source", "old_data", "outside", "interior", "map_note", "boundary_note"]
    return {"states": geography["states"], "districts": {"type": "FeatureCollection", "features": district_features}, "blocks": {"type": "FeatureCollection", "features": blocks}, "points": points, "district": district_name(district, language), "selected_well": station_key, "view": view, "text": {k:t(k, language) for k in keys}, "source": RESOURCE}

def render_map(payload):
    leaflet = (ROOT / "vendor/leaflet.js").read_text()
    css = (ROOT / "vendor/leaflet.css").read_text()
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e')
    return '''<!doctype html><html><head><meta charset="utf-8"><style>''' + css + '''
html,body {margin:0;height:100%;font-family:system-ui,sans-serif;background:#eef5f3}
#map {width:100%;height:100vh;background:#eef5f3}
.leaflet-container {font-family:system-ui,sans-serif}
.block-name {color:#254969;background:#fffffff0;border:1px solid #c5d5df;border-radius:4px;padding:2px 4px;font-size:11px;font-weight:650;width:max-content;white-space:nowrap;transform:translate(-50%,-50%)}
.legend {background:#fffffff2;padding:8px 10px;border-radius:8px;max-width:290px;font-size:12px;line-height:1.6;box-shadow:0 1px 8px #0002}
.map-title {background:#fffffff0;padding:6px 10px;border-radius:7px;font-size:15px;font-weight:700}
.well-popup {font-size:14px;line-height:1.65;max-width:245px}
.well-popup strong {font-size:16px}.well-popup small {color:#657276}
.leaflet-control-layers {font-size:12px;max-width:min(240px,70vw);max-height:45vh;overflow:auto}.leaflet-control-attribution{max-width:80vw;white-space:normal;font-size:9px}.leaflet-bottom.leaflet-left{bottom:24px}
.leaflet-control-layers-toggle {background-image:none!important;display:flex;align-items:center;justify-content:center}
.leaflet-control-layers-toggle::after {content:"☰";font-size:24px;color:#245d66}
</style></head><body><div id="map"></div><script>''' + leaflet + '''</script><script>
const data = ''' + serialized + ''';
const map = L.map('map',{scrollWheelZoom:false,zoomControl:false}).setView([19.2,76.4],6);
map.attributionControl.addAttribution('geoBoundaries: ADM2/3 © Pathways Data / LGD, ODbL 1.0; ADM1 © DataMeet/ECI, CC BY 2.5 IN');
L.control.zoom({zoomInTitle:data.text.zoom_in,zoomOutTitle:data.text.zoom_out}).addTo(map);
const states = L.geoJSON(data.states,{style:{color:'#bbc9c7',weight:1,fillColor:'#e4eeea',fillOpacity:0.75}}).addTo(map);
const allDistricts = L.geoJSON(data.districts,{style:f=>({color:f.properties.selected?'#167eb5':'#849f9a',weight:f.properties.selected?3:1,fillColor:f.properties.selected?'#76c6e5':'#dae9e2',fillOpacity:f.properties.selected?0.6:0.7}),onEachFeature:(f,l)=>l.bindTooltip(f.properties.label)}).addTo(map);
const selectedFeatures = data.districts.features.filter(f=>f.properties.selected);
const selectedDistrict = L.geoJSON({type:'FeatureCollection',features:selectedFeatures});
function inRing(x,y,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if(((a[1]>y)!==(b[1]>y))&&(x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]))inside=!inside;}return inside;}
function inGeometry(x,y,g){const polygons=g.type==='Polygon'?[g.coordinates]:g.coordinates;return polygons.some(poly=>inRing(x,y,poly[0])&&!poly.slice(1).some(hole=>inRing(x,y,hole)));}
const talukas = L.geoJSON(data.blocks,{style:{color:'#4a747e',weight:1,fillOpacity:0},onEachFeature:(f,l)=>l.bindTooltip(f.properties.label)}).addTo(map);
const blockLabels = L.layerGroup();
data.blocks.features.forEach(f=>{
    const node=document.createElement('div');node.className='block-name';node.textContent=f.properties.label;
    L.marker([f.properties.lat,f.properties.lon],{icon:L.divIcon({className:'',html:node.outerHTML,iconSize:[0,0]})}).bindTooltip(f.properties.label+' · '+data.text.interior).addTo(blockLabels);
});
// Block labels are opt-in to keep the map readable.
const wells = L.layerGroup().addTo(map);
let chosen = null;
data.points.forEach(p=>{
    const outside=selectedFeatures.length>0&&!selectedFeatures.some(f=>inGeometry(p.lon,p.lat,f.geometry));
    const popup=document.createElement('div');popup.className='well-popup';
    const title=document.createElement('strong');title.textContent=p.name;popup.appendChild(title);
    function line(label,value){const div=document.createElement('div');div.textContent=label+': '+value;popup.appendChild(div);}
    line(data.text.source_block,p.block);
    line(data.text.depth,p.depth===null?'—':String(p.depth)+' · '+data.text.unit);
    line(data.text.date,p.date);
    if(p.pilot_colour){
      const labels=data.pilot_labels;line(labels[0],p.pilot_target+' · '+(p.pilot_prediction===undefined?'—':p.pilot_prediction.toFixed(2)+' m'));
      if(p.pilot_actual!==undefined)line(labels[1],p.pilot_actual.toFixed(2)+' m');
      const caution=document.createElement('div');caution.textContent=labels[2];popup.appendChild(caution);
    }
    const note=document.createElement('small');note.textContent=data.text.old_data;popup.appendChild(note);
    if(outside){const warning=document.createElement('div');warning.style.color='#a45b00';warning.textContent=data.text.outside;popup.appendChild(warning);}
    popup.appendChild(document.createElement('br'));
    const link=document.createElement('a');link.href=data.source;link.target='_blank';link.rel='noopener';link.textContent=data.text.source+' · CGWB / NWDP';popup.appendChild(link);
    const risk={red:'#c64037',amber:'#d58b20',green:'#338065',grey:'#929e9a'};
    const marker=L.circleMarker([p.lat,p.lon],{radius:p.selected?8:(p.pilot_colour?6:4.5),color:p.pilot_colour?risk[p.pilot_colour]:(p.selected?'#d78c0a':(outside?'#b86b08':'#14764c')),weight:p.selected?3:1,fillColor:p.pilot_colour?risk[p.pilot_colour]:(p.selected?'#fff5b9':(outside?'#df9b2b':'#209d65')),fillOpacity:0.95}).bindTooltip(p.name).bindPopup(popup,{maxWidth:270}).addTo(wells);
    if(p.selected){chosen={point:p,marker};L.circleMarker([p.lat,p.lon],{radius:14,color:'#e4a318',weight:3,fill:false,interactive:false}).addTo(wells);}
});
const historicalWatch=L.layerGroup();
(data.historical_watch||[]).forEach(p=>{
 const node=document.createElement('div');node.textContent=data.watch_label+' · '+String(p.year)+'-'+String(p.month)+' · '+data.text.depth+': '+String(p.predicted_depth.toFixed(2))+' m';
 L.circleMarker([p.latitude,p.longitude],{radius:10,color:'#8b4fa5',weight:2,fillOpacity:.18}).bindPopup(node).addTo(historicalWatch);
});
const reviewTelemetry=L.layerGroup();
(data.review_telemetry||[]).forEach(p=>{
 const node=document.createElement('div');node.textContent=p.station+' · '+data.telemetry_label+' · '+p.date+' · '+String(p.raw_level_m)+' m';
 L.circleMarker([p.latitude,p.longitude],{radius:5,color:'#68659b',weight:1.5,fillColor:'#b8b5d4',fillOpacity:.8}).bindPopup(node).addTo(reviewTelemetry);
});
const overlays={};if(data.review_telemetry)overlays[data.telemetry_label]=reviewTelemetry;if(data.historical_watch)overlays[data.watch_label]=historicalWatch;overlays[data.text.blocks]=talukas;overlays[data.text.block_labels]=blockLabels;overlays[data.text.wells]=wells;
const layerControl=L.control.layers(null,overlays,{collapsed:true}).addTo(map);
const layerToggle=layerControl.getContainer().querySelector(".leaflet-control-layers-toggle");if(layerToggle){layerToggle.title=data.text.blocks;layerToggle.setAttribute("aria-label",data.text.blocks);}
const heading=L.control({position:'topleft'});heading.onAdd=()=>{const d=L.DomUtil.create('div','map-title');d.textContent=data.district;return d;};heading.addTo(map);
const legend=L.control({position:'bottomleft'});legend.onAdd=()=>{const d=L.DomUtil.create('div','legend');d.textContent=data.text.map_note;return d;}; // Legend is displayed below the map in the dashboard.
L.control.scale({imperial:false}).addTo(map);
function focus(){
 map.invalidateSize();
 if(data.view==='india'){map.fitBounds(states.getBounds(),{padding:[20,20]});}
 else if(data.view==='well' && chosen){map.setView([chosen.point.lat,chosen.point.lon],11);chosen.marker.openPopup();}
 else if(data.view==='district' && selectedFeatures.length){map.fitBounds(selectedDistrict.getBounds(),{padding:[35,35],maxZoom:10});}
 else{map.fitBounds(allDistricts.getBounds(),{padding:[25,25]});}
}
setTimeout(focus,80);window.addEventListener('resize',()=>map.invalidateSize());
</script></body></html>'''
