"""Official airport statistics ingestion. No imputation; atomic validated snapshot."""
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests, bs4, pymupdf, re, json, csv, io, hashlib, unicodedata, argparse, calendar

ROOT=Path(__file__).resolve().parents[1] if Path(__file__).parent.name=='pipeline' else Path(__file__).parent
CACHE=ROOT/'.cache'/'sources';CACHE.mkdir(parents=True,exist_ok=True)
NOW=datetime.now(timezone.utc); START=2023
AIRPORTS=[('AGP','Málaga','LEMG','Andalucía'),('SVQ','Sevilla','LEZL','Andalucía'),('GRX','Granada-Jaén','LEGR','Andalucía'),('LEI','Almería','LEAM','Andalucía'),('XRY','Jerez','LEJR','Andalucía'),('ODB','Córdoba','LEBA','Andalucía'),('GIB','Gibraltar','LXGB','Gibraltar'),('MAD','Madrid-Barajas','LEMD','Referencia nacional'),('BCN','Barcelona-El Prat','LEBL','Referencia nacional')]
ALIASES={'AGP':['MALAGA'],'SVQ':['SEVILLA','SEVILLE'],'GRX':['GRANADA'],'LEI':['ALMERIA'],'XRY':['JEREZ'],'ODB':['CORDOBA'],'MAD':['MADRID-BARAJAS','MADRID BARAJAS','MADRID'],'BCN':['BARCELONA'],'GIB':['GIBRALTAR']}
ESMONTHS=['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
ENMONTHS=[calendar.month_name[m] for m in range(1,13)]
WARN=[]
def normal(s):return ''.join(c for c in unicodedata.normalize('NFD',s.upper()) if unicodedata.category(c)!='Mn')
def code(name):
 n=normal(name)
 if 'CUATRO' in n or 'SABADELL' in n:return None
 return next((k for k,vs in ALIASES.items() if any(v in n for v in vs)),None)
def fetch(url,cache=True):
 p=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.bin')
 if cache and p.exists() and NOW.timestamp()-p.stat().st_mtime<30*86400:return p.read_bytes()
 error=None
 for _ in range(2):
  try:
   r=requests.get(url,timeout=(12,50),headers={'User-Agent':'ObservatorioAereo/1.0 (public statistical research)'})
   r.raise_for_status(); b=r.content
   if len(b)<20:raise ValueError('Empty response')
   p.write_bytes(b);return b
  except Exception as e:error=e
 raise error
def soup(url,cache=False):return bs4.BeautifulSoup(fetch(url,cache),'html.parser')
def words_lines(page):
 lines=[]
 for w in sorted(page.get_text('words'),key=lambda w:(w[1],w[0])):
  match=next((x for x in lines[-5:] if abs(x[0]-w[1])<1.8),None)
  if match:match[1].append(w)
  else:lines.append([w[1],[w]])
 return [(y,sorted(ws,key=lambda w:w[0])) for y,ws in lines]
def num(x):return int(re.sub(r'[.,\s]','',x)) if re.fullmatch(r'[\d.,\s]+',x) else None
def parse_aena(b,url,expected_year):
 d=pymupdf.open(stream=b,filetype='pdf');p=d[0];txt=normal(p.get_text(sort=True))
 m=re.search(r'('+'|'.join(x.upper() for x in ESMONTHS)+r')\s+DE\s+(20\d{2})',txt)
 if not m:raise ValueError('Missing monthly header')
 year=int(m[2]); month=ESMONTHS.index(m[1].lower())+1
 if year!=expected_year:raise ValueError('Wrong report year')
 groups=[(y,[w for w in ws if w[4].lower()=='total']) for y,ws in words_lines(p) if y<p.rect.height*.3]
 headers=next((ws for y,ws in groups if len(ws)==3),[])
 if len(headers)!=3:raise ValueError(f'Expected 3 metric columns, found {len(headers)}')
 starts=[w[0] for w in headers]
 pitch=starts[1]-starts[0];boundaries=[starts[0]-pitch*.8,starts[1]-pitch*.8,starts[2]-pitch*.8,p.rect.width+1]
 vals={k:{} for k,*_ in AIRPORTS if k!='GIB'}
 for y,ws in words_lines(p):
  if y<=headers[0][1]+5:continue
  for ci,metric in enumerate(['passengers','operations','cargoKg']):
   seg=[w[4] for w in ws if boundaries[ci]<=w[0]<boundaries[ci+1]]
   if not seg:continue
   i=next((i for i,v in enumerate(seg) if re.fullmatch(r'\d[\d.]*',v)),None)
   if i is None:continue
   c=code(' '.join(seg[:i]))
   if c in vals:
    if metric in vals[c]:raise ValueError(f'Duplicate {c} {metric}')
    vals[c][metric]=num(seg[i])
 if any(len(v)!=3 for v in vals.values()):raise ValueError(f'Incomplete Aena parse {year}-{month}: {vals}')
 return [dict(airport=k,month=f'{year}-{month:02}',**v,arrivals=None,departures=None,provider='Aena',sourceUrl=url) for k,v in vals.items()]
def aena_jobs(year):
 u=f'https://www.aena.es/es/estadisticas/informes-mensuales.html?anio={year}'
 s=soup(u,cache=year<NOW.year-1)
 return [(urljoin(u,a['href']),year) for a in s.select('a[href]') if a.get_text(strip=True).startswith('PDF')]
def parse_gib(b,url,year):
 d=pymupdf.open(stream=b,filetype='pdf'); rows=[]
 for y,ws in words_lines(d[0]):
  tokens=[w[4] for w in ws];hits=[i for i,v in enumerate(tokens) if v in ENMONTHS]
  if len(hits)!=3:continue
  month=ENMONTHS.index(tokens[hits[0]])+1
  parts=[tokens[hits[j]+1:hits[j+1] if j<2 else len(tokens)] for j in range(3)]
  nums=[[num(v) for v in part if re.fullmatch(r'[\d,]+',v)] for part in parts]
  if len(nums[0])<8 or len(nums[1])<2 or len(nums[2])<2:continue
  for offset in (0,1):
   yy=year-offset;p=nums[0][offset*4:offset*4+4]
   if yy<START or f'{yy}-{month:02}' >= NOW.strftime('%Y-%m'):continue
   if p[0]+p[1]!=p[2]:raise ValueError('Gibraltar arrivals/departures mismatch')
   if p[2]==0:continue # future unfilled months are zero in some reports; no zero inference
   rows.append(dict(airport='GIB',month=f'{yy}-{month:02}',passengers=p[2],operations=nums[2][offset],cargoKg=nums[1][offset],arrivals=p[0],departures=p[1],provider='Gibraltar Airport',sourceUrl=url,reportYear=year))
 if not rows:raise ValueError('No Gibraltar monthly rows')
 return rows
def gib_jobs():
 u='https://gibraltarairport.gi/about-us/air-traffic-statistics';s=soup(u)
 return [(urljoin(u,a['href']),int(m[1])) for a in s.select('a[href]') if (m:=re.search(r'(20\d{2}) AIR TRAFFIC STATISTICS',a.get_text())) and int(m[1])>=START]
def decode_stat(d):
 ids=d['id'];sizes=d['size'];codes=[]
 for k in ids:
  idx=d['dimension'][k]['category']['index'];codes.append([c for c,i in sorted(idx.items(),key=lambda x:x[1])])
 for flat,val in d.get('value',{}).items():
  n=int(flat);coords=[]
  for size in reversed(sizes):coords.append(n%size);n//=size
  yield {k:codes[j][i] for j,(k,i) in enumerate(zip(ids,reversed(coords)))},val
def euro(code_,icao,kind):
 dataset='avia_paoac' if kind=='countries' else 'avia_paoa'
 params={'lang':'EN','freq':'M','unit':'PAS','tra_meas':'PAS_CRD','rep_airp':'ES_'+icao,'sinceTimePeriod':f'{START}-01'}
 if kind=='mix':params['schedule']='TOTAL'
 u=requests.Request('GET',f'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}',params=params).prepare().url
 d=json.loads(fetch(u,False));out=[]
 if 'rep_airp' not in d['id']:raise ValueError('Unverified airport dimension')
 for c,v in decode_stat(d):
  if c['rep_airp']!='ES_'+icao or not re.fullmatch(r'20\d{2}-\d{2}',c['time']):continue
  if kind=='countries':
   partner=c['partner']
   if len(partner)!=2:continue # exclude overlapping EU totals
   label=d['dimension']['partner']['category']['label'].get(partner,partner)
   out.append(dict(airport=code_,month=c['time'],country=partner,countryLabel=label,passengers=v,provider='Eurostat',sourceUrl=u))
  elif c['tra_cov'] in ('NAT','INTL'):
   out.append(dict(airport=code_,month=c['time'],market=c['tra_cov'],passengers=v,provider='Eurostat',sourceUrl=u))
 return out
def caa_month(year,month):
 slug=ENMONTHS[month-1].lower();u=f'https://www.caa.co.uk/data-and-analysis/uk-aviation-market/airports/uk-airport-data/uk-airport-data-{year}/{slug}-{year}/'
 s=soup(u,cache=year<NOW.year or month<NOW.month-2)
 links=[a for a in s.select('a[href]') if '12 1' in a.get_text() and 'CSV' in a.get_text()]
 if not links:return []
 link=urljoin(u,links[0]['href']);text=fetch(link,cache=year<NOW.year or month<NOW.month-2).decode('utf-8-sig')
 out=[]
 for r in csv.DictReader(io.StringIO(text.replace('\r\r\n','\n'))):
  c=code(r.get('foreign_airport',''))
  if c is None or r.get('foreign_country') not in ('SPAIN','GIBRALTAR'):continue
  period=r['this_period'];
  if period!=f'{year}{month:02}':raise ValueError('Wrong CAA reporting period')
  out.append(dict(airport=c,month=f'{year}-{month:02}',ukAirport=r['UK_airport'],passengers=int(r['total_pax_this_period']),scheduled=int(r['total_pax_scheduled_this_period']),charter=int(r['total_pax_charter_this_period']),provider='UK CAA',sourceUrl=link))
 return out
def run_jobs(tasks):
 out=[]
 with ThreadPoolExecutor(max_workers=5) as ex:
  fs={ex.submit(fn,*args):label for label,fn,args in tasks}
  for f in as_completed(fs):
   label=fs[f]
   try:r=f.result();out+=r;print(label,len(r),flush=True)
   except Exception as e:WARN.append(f'{label}: {type(e).__name__}: {e}');print('WARNING',WARN[-1],flush=True)
 return out
def source(label,rows,notes):
 months=sorted({r['month'] for r in rows});urls=sorted({r['sourceUrl'] for r in rows})
 return dict(label=label,provider=label,executedAt=NOW.isoformat(),coverage=dict(startDate=months[0]+'-01' if months else None,endDate=months[-1]+'-01' if months else None),files=urls,notes=notes,evidenceFlow=[dict(title='Publicaciones oficiales',detail='Descarga HTTP de las URL sourceUrl guardadas en cada fila. Extracción reproducible mediante pipeline/refresh.py; sin estimaciones ni imputación.')],metricDefinitions=[dict(label='Pasajeros',definition='Movimientos de pasajeros de llegada y salida. No son personas únicas ni turistas.'),dict(label='Operaciones',definition='Aterrizajes más despegues. Incluye aviación no comercial según la fuente.'),dict(label='Carga (kg)',definition='Aena: mercancías. Gibraltar: carga, correo y mensajería; perímetros diferentes.')])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'src'/'data.json');ap.add_argument('--core-only',action='store_true');args=ap.parse_args()
 previous=json.loads(args.output.read_text(encoding='utf8')) if args.output.exists() else None
 tasks=[]
 for y in range(START,NOW.year+1):
  try:
   for u,yy in aena_jobs(y):tasks.append((f'Aena {yy} {u[-30:]}',lambda u,y:parse_aena(fetch(u,cache=y<NOW.year),u,y),(u,yy)))
  except Exception as e:WARN.append(f'Aena discovery {y}: {e}')
 try:
  for u,y in gib_jobs():tasks.append((f'Gibraltar {y}',lambda u,y:parse_gib(fetch(u,cache=y<NOW.year),u,y),(u,y)))
 except Exception as e:WARN.append(f'Gibraltar discovery: {e}')
 core=run_jobs(tasks)
 # Higher report year can revise prior year; prefer the newest published report.
 keyed={}
 for row in sorted(core,key=lambda r:r.get('reportYear',0)):keyed[row['airport'],row['month']]=row
 core=sorted(keyed.values(),key=lambda r:(r['month'],r['airport']))
 if len(core)<100:raise RuntimeError('Insufficient common data; keep previous snapshot')
 queryrows={'traffic':core}
 if not args.core_only:
  for kind in ('countries','mix'):
   queryrows[kind]=run_jobs([(f'Eurostat {kind} {c}',euro,(c,icao,kind)) for c,n,icao,g in AIRPORTS if c!='GIB'])
  queryrows['uk_routes']=run_jobs([(f'CAA {y}-{m:02}',caa_month,(y,m)) for y in range(max(START,NOW.year-2),NOW.year+1) for m in range(1,13) if f'{y}-{m:02}'<NOW.strftime('%Y-%m')])
 else:
  queryrows.update(countries=[],mix=[],uk_routes=[])
 notes={'traffic':['La carga de Gibraltar incluye correo y mensajería: no es estrictamente equivalente a mercancías Aena.','Datos mensuales publicados, sujetos a revisión. No se infieren valores de meses ausentes.'], 'countries':['Eurostat avia_paoac: solo países socios declarantes europeos, no todos los destinos mundiales. País del vuelo, no nacionalidad. No sumar agregados UE.'], 'mix':['Eurostat avia_paoa, pasajeros transportados, vuelos regulares y no regulares. Cobertura propia, puede diferir de Aena.'], 'uk_routes':['CAA tabla 12.1: pasajeros entre aeropuertos británicos y el aeropuerto seleccionado, ambos sentidos. No mide toda la red. No sumar con Aena/Gibraltar: son poblaciones solapadas.']}
 labels={'traffic':'Aena y Gibraltar Airport','countries':'Eurostat · países socios europeos','mix':'Eurostat · nacional e internacional','uk_routes':'UK Civil Aviation Authority · tabla 12.1'}
 # Retain previously verified observations if a provider temporarily fails; never erase history.
 for q,rs in queryrows.items():
  keyfields={'traffic':['airport','month'],'countries':['airport','month','country'],'mix':['airport','month','market'],'uk_routes':['airport','month','ukAirport']}[q]
  prev=previous.get('queries',{}).get(q,{}).get('rows',[]) if previous else []
  merged={tuple(r[k] for k in keyfields):r for r in prev}
  merged.update({tuple(r[k] for k in keyfields):r for r in rs});queryrows[q]=sorted(merged.values(),key=lambda r:tuple(r[k] for k in keyfields))
 data=dict(id=previous.get('id','observatorio-aereo-andalucia-espana') if previous else 'observatorio-aereo-andalucia-espana',surface='dashboard',title='Observatorio aéreo',status='reviewed',buildStatus='creating' if args.core_only else 'complete',generatedAt=NOW.isoformat(),filters=[],airports=[dict(code=c,name=n,icao=i,group=g) for c,n,i,g in AIRPORTS],refresh=dict(checkedAt=NOW.isoformat(),warnings=WARN,cadence='Diaria · 07:20 UTC'),queries={q:dict(rows=rs,source=source(labels[q],rs,notes[q]),methods=[dict(language='python',code='pipeline/refresh.py: descargar fuentes, validar periodos, extraer valores, deduplicar por aeropuerto y mes. Conservar registros anteriores ante fallos parciales.')]) for q,rs in queryrows.items()})
 for c,*_ in AIRPORTS:
  if not any(r['airport']==c for r in data['queries']['traffic']['rows']):raise ValueError(f'Missing airport {c}')
 for q,rs in queryrows.items():
  for r in rs:
   for field in ('passengers','operations','cargoKg','arrivals','departures','scheduled','charter'):
    v=r.get(field)
    if v is not None and (not isinstance(v,(int,float)) or v<0):raise ValueError(f'Invalid {field}')
 args.output.parent.mkdir(parents=True,exist_ok=True); tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(args.output)
 print('SAVED',args.output,{q:len(rs) for q,rs in queryrows.items()},'warnings',len(WARN),flush=True)
if __name__=='__main__':main()
