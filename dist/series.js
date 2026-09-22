/* Shared catalog grouping; episode records and IDs remain unchanged. */
(function(root){'use strict';
function key(value){return String(value||'').normalize('NFC').trim().replace(/\s+/g,' ').toLowerCase()}
function same(a,b){return a.kind==='series'&&b.kind==='series'&&key(a.series)!==''&&key(a.series)===key(b.series)}
function order(a,b){return Number(a.season)-Number(b.season)||Number(a.episode)-Number(b.episode)||String(a.id).localeCompare(String(b.id))}
function episodes(items,item){return items.filter(function(x){return same(x,item)}).sort(order)}
function groups(items){var result=[],lookup=Object.create(null);items.forEach(function(v){var k=v.kind==='series'&&key(v.series)?'series:'+key(v.series):'video:'+v.id;if(!lookup[k]){lookup[k]={key:k,series:v.kind==='series'&&!!key(v.series),items:[]};result.push(lookup[k])}lookup[k].items.push(v)});result.forEach(function(g){g.items.sort(order);g.first=g.items[0];g.name=g.series?g.first.series.trim():g.first.name});return result}
function next(items,name,season){var matches=items.filter(function(v){return v.kind==='series'&&key(v.series)===key(name)&&Number(v.season)===Number(season)});return matches.reduce(function(n,v){return Math.max(n,Number(v.episode)||0)},0)+1}
var api={key:key,same:same,order:order,episodes:episodes,groups:groups,next:next};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LumaSeries=api;
})(typeof window!=='undefined'?window:this);
