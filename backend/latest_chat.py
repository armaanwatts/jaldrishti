"""Deterministic answers about source recency; never turn raw telemetry into advice."""
from pathlib import Path
import re
import json
import pandas as pd
from core import ROOT,_digit_normalize
from i18n import district_name

def latest_reply(question,districts,language,station=None):
    q=_digit_normalize(question).casefold()
    terms=['today','current','latest','now','आज','अभी','ताजा','ताज़ा','नवीन','सध्या','आत्ता','ताजी']
    if not any(term in q for term in terms):return None
    if any(term in q for term in ['predict','forecast','future','tomorrow','next season','भविष्य','उद्या','अंदाज']):return None
    years=[int(x) for x in re.findall(r'\b(?:19|20)\d{2}\b',q)]
    if years and max(years)<2026:return None
    path=ROOT/'data/latest_telemetry_stations.csv';manifest_path=ROOT/'data/latest_source_manifest.json'
    if not path.exists() or not manifest_path.exists():return None
    if station:
        text={'English':'The selected manual monitoring well has no verified identity match to the newer telemetry. Its latest historical record cannot establish today’s water depth.', 'Hindi':'चुने गए पुराने निगरानी कुएँ का नई टेलीमेट्री से पक्का मिलान नहीं है। पुराने माप से आज की गहराई नहीं बता सकते।','Marathi':'निवडलेल्या जुन्या निरीक्षण विहिरीची नव्या टेलिमेट्रीशी खात्रीशीर ओळख जुळलेली नाही. जुन्या नोंदींवरून आजची खोली सांगता येत नाही.'}[language]
        return {'answer':text,'facts':[],'generated':False}
    data=pd.read_csv(path);manifest=json.loads(manifest_path.read_text());facts=[];answers=[]
    for district in districts:
        selected=data[data.district.eq(district)]
        if selected.empty:continue
        date=str(selected.date.max())[:10];name=district_name(district,language)
        first=str(selected.date.min())[:10]
        fact={'id':f'R{len(facts)+1}','label':district,'source':manifest['source_url'],'first_date':first,'last_date':date,'station_count':len(selected),'measurement_count':len(selected),'kind':'Latest raw telemetry row per independent source station, not verified depth below ground','current_supported':False,'forecast_supported':False,'measurement_convention_verified':False,'independent_of_manual_well_ids':True}
        facts.append(fact)
        templates={'English':f'For {name}, the newest reading in the downloaded telemetry snapshot is dated {date}. It is not a live reading. The signed source values still need checking, so I cannot confirm today’s groundwater depth or give a crisis warning from them.',
        'Hindi':f'{name} के डाउनलोड किए टेलीमेट्री रिकॉर्ड में सबसे नया माप {date} का है। यह लाइव माप नहीं है। मानों के अर्थ की जाँच बाकी है, इसलिए इनसे आज की भूजल गहराई या संकट की चेतावनी की पुष्टि नहीं कर सकते।',
        'Marathi':f'{name} च्या डाउनलोड केलेल्या टेलिमेट्री नोंदींमधील सर्वात नवी मोजणी {date} ची आहे. ती थेट आजची मोजणी नाही. मूल्यांचा अर्थ तपासायचा आहे, त्यामुळे त्यावरून आजची भूजल खोली किंवा संकटाचा इशारा निश्चित करता येत नाही.'}
        answers.append(templates[language])
    if not answers:return None
    return {'answer':'\n\n'.join(answers),'facts':facts,'generated':False}
