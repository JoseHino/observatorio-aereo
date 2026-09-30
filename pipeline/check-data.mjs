import fs from 'node:fs';
import assert from 'node:assert/strict';
import {commonMonths,delta,shiftMonth,sumComplete,annualRows} from '../src/content/dashboard/airport-data.js';
const d=JSON.parse(fs.readFileSync(new URL('../src/data.json',import.meta.url)));
const codes=d.airports.map(a=>a.code),t=d.queries.traffic.rows;
assert.equal(codes.length,9);
for(const[q,v]of Object.entries(d.queries)){
 const dims={traffic:['airport','month'],countries:['airport','month','country'],mix:['airport','month','market'],uk_routes:['airport','month','ukAirport']}[q];
 const keys=v.rows.map(r=>dims.map(k=>r[k]).join('|'));assert.equal(new Set(keys).size,keys.length,`Duplicates ${q}`);
 for(const r of v.rows){assert(codes.includes(r.airport));assert(/^20\d{2}-\d{2}$/.test(r.month));assert(r.sourceUrl.startsWith('https://'));for(const k of ['passengers','operations','cargoKg'])if(r[k]!=null)assert(r[k]>=0&&Number.isFinite(r[k]));}
}
for(const c of codes)assert(t.some(r=>r.airport===c),`Missing ${c}`);
for(const r of t.filter(r=>r.airport==='GIB'))assert.equal(r.arrivals+r.departures,r.passengers);
const gib=t.filter(r=>r.airport==='GIB'&&r.month.startsWith('2025'));
assert.equal(gib.length,12);assert.equal(gib.reduce((a,r)=>a+r.passengers,0),437172,'Official Gibraltar 2025 total');
assert.equal(t.find(r=>r.airport==='MAD'&&r.month==='2025-01').passengers,5198143,'Official Aena Jan 2025');
assert.equal(shiftMonth('2025-01',-1),'2024-12');assert.equal(delta(10,0),null);assert.equal(delta(null,10),null);assert.equal(delta(110,100).toFixed(1),'10.0');
const fixture=[{airport:'A',month:'2025-01',passengers:5},{airport:'B',month:'2025-02',passengers:10}];
assert.deepEqual(commonMonths(fixture,['A','B']),[]);assert.equal(sumComplete(fixture,['A','B'],'2025-01','passengers'),null);assert.equal(annualRows(fixture,['A'],2,'passengers',x=>x)[0].Pasajeros,null);
const latest=commonMonths(t,codes).at(-1);assert(latest,'No common month');
console.log(JSON.stringify({passed:true,latestCommonMonth:latest,counts:Object.fromEntries(Object.entries(d.queries).map(([k,v])=>[k,v.rows.length]))}));
