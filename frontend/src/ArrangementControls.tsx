import {useEffect,useRef,useState} from 'react'
import {api,jsonPost} from './api'
import {noteName} from './timing'
import type {Arrangement,ArrangementList,ArrangementSettings,Difficulty,Guidance,Hand,HandDifficulty,Piece} from './types'

export const levelNames:Record<Difficulty,string>={melody:'Melody only',beginner:'Beginner',easy:'Easy',full:'Full transcription'}
export function handPreset(level:Difficulty,hand:Hand):HandDifficulty {
 return {level,maxNotes:level==='easy'?(hand==='left'?2:3):level==='full'?5:1,maxSpan:level==='full'?12:7,activity:level==='melody'?'none':level==='easy'?'light':'changes'}
}
function preset(level:Difficulty):ArrangementSettings{return {left:handPreset(level,'left'),right:handPreset(level,'right')}}
export function difficultyLabel(settings:ArrangementSettings){
 const {left,right}=settings
 const custom=JSON.stringify(settings)!==JSON.stringify(preset(left.level))
 return !custom&&left.level===right.level?levelNames[left.level]:`Customized · L: ${levelNames[left.level]} · R: ${levelNames[right.level]}`
}
const emptyGuidance=():Guidance=>({roles:{},protectedNoteIds:[]})
const stamp=(t:number)=>`${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`

export function ArrangementControls({piece,online,selected,comparing,loopA,loopB,onChange,onCompare,onSeek,onCorrect,onSourceUpdated}:{
 piece:Piece;online:boolean;selected?:Arrangement;comparing:boolean;loopA:number;loopB:number;
 onChange:(a?:Arrangement)=>void;onCompare:(full:boolean)=>void;onSeek:(t:number)=>void;onCorrect:(id:string)=>void;onSourceUpdated:(p:Piece)=>void
}){
 const [open,setOpen]=useState(false),[list,setList]=useState<ArrangementList>(),[settings,setSettings]=useState(preset('beginner'))
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[name,setName]=useState('Beginner arrangement')
 const [guidance,setGuidance]=useState<Guidance>(piece.guidance??emptyGuidance()),[start,setStart]=useState(0),[end,setEnd]=useState(Math.min(10,piece.duration))
 const [reviewId,setReviewId]=useState(''),[page,setPage]=useState(0)
 const changeRef=useRef(onChange);changeRef.current=onChange
 const key=`piano-arrangement-${piece.id}`
 useEffect(()=>{
  let alive=true
  setGuidance(piece.guidance??emptyGuidance())
  if(!online)return
  void api<ArrangementList>(`/pieces/${piece.id}/arrangements`).then(async next=>{
   if(!alive)return
   setList(next);setGuidance(next.guidance)
   const saved=localStorage.getItem(key)
   if(saved&&next.arrangements.some(a=>a.id===saved)){
    const a=await api<Arrangement>(`/pieces/${piece.id}/arrangements/${saved}`)
    if(alive){setSettings(a.settings);setName(a.name);changeRef.current(a)}
   }else if(saved){localStorage.removeItem(key);changeRef.current(undefined)}
  }).catch(e=>{if(alive)setError(String(e.message??e))})
  return()=>{alive=false}
 },[piece,online,key])
 async function select(id:string){
  setBusy(true);setError('')
  try{if(!id){localStorage.removeItem(key);onChange(undefined)}else{const a=await api<Arrangement>(`/pieces/${piece.id}/arrangements/${id}`);localStorage.setItem(key,id);setSettings(a.settings);setName(a.name);onChange(a)}}catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function generate(refresh=false){
  if(!list)return
  setBusy(true);setError('')
  try{
   const a=await api<Arrangement>(`/pieces/${piece.id}/arrangements`,jsonPost({settings:refresh&&selected?selected.settings:settings,expectedSourceFingerprint:list.sourceFingerprint,name:refresh&&selected?selected.name:name,predecessorId:refresh?selected?.id:undefined}))
   localStorage.setItem(key,a.id);onChange(a);setPage(0)
   setList(await api<ArrangementList>(`/pieces/${piece.id}/arrangements`))
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function saveGuidance(){
  if(!list)return
  setBusy(true);setError('')
  try{
   await api(`/pieces/${piece.id}/guidance`,{...jsonPost({guidance,expectedSourceFingerprint:list.sourceFingerprint}),method:'PUT'})
   onSourceUpdated(await api<Piece>(`/pieces/${piece.id}`))
  }catch(e){setError(String(e))}finally{setBusy(false)}
 }
 async function remove(){
  if(!selected||!window.confirm(`Delete “${selected.name}”? The source transcription and other versions stay saved.`))return
  setBusy(true);setError('')
  try{await api(`/pieces/${piece.id}/arrangements/${selected.id}`,{method:'DELETE'});localStorage.removeItem(key);onChange(undefined);setList(await api<ArrangementList>(`/pieces/${piece.id}/arrangements`))}catch(e){setError(String(e))}finally{setBusy(false)}
 }
 const sourceNotes=piece.notes
 const protectedSet=new Set(guidance.protectedNoteIds)
 const passage=sourceNotes.filter(n=>n.start>=start&&n.start<end)
 const suggestedMelody=new Set(selected?.melodyNoteIds??[])
 const updateHand=(hand:Hand,patch:Partial<HandDifficulty>)=>setSettings({...settings,[hand]:{...settings[hand],...patch}})
 const review=sourceNotes.find(n=>n.id===reviewId)
 return <section className="arrangement-bar" aria-label="Arrangement">
  <div className="arrangement-actions"><button className="secondary small" onClick={()=>setOpen(true)}>Simplify arrangement</button>
   <label>Arrangement<select aria-label="Selected arrangement" disabled={busy||!online} value={selected?.id??''} onChange={e=>void select(e.target.value)}><option value="">Full transcription</option>{list?.arrangements.map(a=><option key={a.id} value={a.id}>{a.name}{a.outdated?' · source changed':''}</option>)}</select></label>
   {selected&&<div className="comparison-buttons" role="group" aria-label="Listening comparison"><button aria-pressed={comparing} onClick={()=>onCompare(true)}>Full transcription</button><button aria-pressed={!comparing} onClick={()=>onCompare(false)}>Selected arrangement</button></div>}
  </div>
  {selected&&<small>{difficultyLabel(selected.settings)}{comparing?' · Listening to this arrangement’s full source transcription':''}{selected.outdated?' · Source changed; saved arrangement preserved':''}</small>}
  {error&&!open&&<p className="notice error">{error}</p>}
  {open&&<div className="modal-backdrop" onClick={()=>{if(!busy)setOpen(false)}}><section className="modal arrangement-modal" role="dialog" aria-modal="true" aria-label="Simplify arrangement" onClick={e=>e.stopPropagation()}>
   <header className="modal-header"><h2>Simplify arrangement</h2><button className="icon-button" disabled={busy} aria-label="Close arrangement settings" onClick={()=>setOpen(false)}>×</button></header>
   <div className="arrangement-content">
   <p>Keep the tune, reduce the playing demands. Each arrangement is saved separately. Retained melody timing stays unchanged.</p>
   <div className="preset-buttons" role="group" aria-label="Difficulty preset">{(Object.keys(levelNames) as Difficulty[]).map(level=><button key={level} aria-pressed={JSON.stringify(settings)===JSON.stringify(preset(level))} onClick={()=>{setSettings(preset(level));setName(`${levelNames[level]} arrangement`)}}>{levelNames[level]}</button>)}</div>
   <div className="field-row">{(['left','right'] as Hand[]).map(hand=><label key={hand}>{hand==='left'?'Left':'Right'}-hand difficulty<select aria-label={`${hand==='left'?'Left':'Right'}-hand difficulty`} value={settings[hand].level} onChange={e=>setSettings({...settings,[hand]:handPreset(e.target.value as Difficulty,hand)})}>{Object.entries(levelNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>)}</div>
   <details><summary>Advanced arrangement settings</summary><div className="hand-difficulty-grid">{(['left','right'] as Hand[]).map(hand=><fieldset key={hand} disabled={settings[hand].level==='full'}><legend>{hand==='left'?'Left':'Right'} hand</legend><label>Most notes played together<input aria-label={`${hand} most notes played together`} type="number" min="1" max="5" value={settings[hand].maxNotes} onChange={e=>updateHand(hand,{maxNotes:+e.target.value})}/></label><label>Largest stretch<select aria-label={`${hand} largest stretch`} value={settings[hand].maxSpan} onChange={e=>updateHand(hand,{maxSpan:+e.target.value})}>{[[0,'One key'],[5,'Close · up to a fourth'],[7,'Up to a fifth'],[9,'Up to a sixth'],[12,'Up to an octave'],[24,'Up to two octaves']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label>Accompaniment activity<select aria-label={`${hand} accompaniment activity`} value={settings[hand].activity} onChange={e=>updateHand(hand,{activity:e.target.value as HandDifficulty['activity']})}><option value="none">None</option><option value="changes">Important chord changes</option><option value="light">Light movement</option></select></label></fieldset>)}</div><p className="fine-print">Essential and protected melody takes priority over these limits. Remaining stretches and jumps are flagged. Rhythm changes are not applied; replacement accompaniment releases may be shortened. Original pedal events are preserved.</p></details>
   <label>Arrangement name<input maxLength={160} value={name} onChange={e=>setName(e.target.value)}/></label>
   <div className="button-row"><button className="primary" disabled={busy||!online||!list||!name.trim()} onClick={()=>void generate()}>{busy?'Working…':'Generate & save arrangement'}</button>{selected&&<><button className="secondary" disabled={busy||!online} onClick={()=>void generate(true)}>Refresh as new version</button><button className="quiet danger" disabled={busy||!online} onClick={()=>void remove()}>Delete arrangement</button></>}</div>
   {selected&&<section><h3>Playing demands</h3><p>{selected.name}{selected.outdated?' · Based on an older source revision. Refresh explicitly to apply your corrections.':''}</p><div className="metrics-scroll"><table className="demand-table"><thead><tr><th>Demand</th><th>Left: source → arrangement</th><th>Right: source → arrangement</th></tr></thead><tbody>{([['noteCount','Notes'],['maxSimultaneous','Most simultaneous notes'],['maxSpan','Largest stretch (semitones)'],['largeJumps','Jumps over an octave'],['accompanimentAttacksPerSecond','Accompaniment notes / second']] as const).map(([key,label])=><tr key={key}><th>{label}</th>{(['left','right'] as Hand[]).map(hand=><td key={hand}>{selected.metrics.before[hand][key]} → {selected.metrics.after[hand][key]}</td>)}</tr>)}</tbody></table></div>
    <h3>Passages to review ({selected.reviewFlags.length})</h3><p className="fine-print">These are musical estimates, not confidence probabilities. Listen for the intended melody, harmony, ornaments, and comfortable hand movement.</p>
    {selected.reviewFlags.slice(page*15,page*15+15).map((flag,i)=><div className="review-passage" key={`${page}-${i}`}><button className="quiet" onClick={()=>onSeek(flag.start)}>Measure {selected.performance.score.measures.findLast(m=>m.startTime<=flag.start)?.number??1} · {stamp(flag.start)}</button><p>{flag.message}</p><button className="quiet" onClick={()=>{const id=flag.noteIds.find(id=>sourceNotes.some(n=>n.id===id));if(id)setReviewId(id)}}>Inspect source notes</button></div>)}
    {selected.reviewFlags.length>15&&<div className="button-row"><button disabled={!page} onClick={()=>setPage(page-1)}>Previous passages</button><button disabled={(page+1)*15>=selected.reviewFlags.length} onClick={()=>setPage(page+1)}>More passages</button></div>}
    <details><summary>Why notes changed ({selected.operations.length})</summary>{selected.operations.slice(0,100).map((op,i)=><p className="fine-print" key={i}><button className="quiet" onClick={()=>setReviewId(op.sourceNoteIds[0])}>{op.sourceNoteIds.join(', ')}</button> {op.message}{op.before!==undefined?` ${op.before} → ${op.after}`:''}</p>)}{selected.operations.length>100&&<p>Showing the first 100 changes. Every source note remains available below.</p>}</details>
   </section>}
   <section><h3>Melody guidance & protection</h3><p className="fine-print">Shared by future arrangements of this piece. Saving guidance preserves existing arrangements until you refresh them.</p><label>Review a source note (including omitted notes)<select aria-label="Review source note" value={reviewId} onChange={e=>setReviewId(e.target.value)}><option value="">Choose a source note…</option>{sourceNotes.map(n=><option key={n.id} value={n.id}>{noteName(n.pitch)} · {stamp(n.start)} · {n.hand}{selected&&!selected.performance.notes.some(a=>a.id===n.id)?' · omitted':''}</option>)}</select></label>
    {review&&<div className="source-review"><p>{noteName(review.pitch)} · {review.start.toFixed(3)}–{review.end.toFixed(3)}s · {review.hand} hand</p><label>Musical role<select aria-label="Source note musical role" value={guidance.roles[review.id]??'auto'} onChange={e=>{const roles={...guidance.roles};if(e.target.value==='auto')delete roles[review.id];else roles[review.id]=e.target.value as 'melody'|'accompaniment';setGuidance({...guidance,roles})}}><option value="auto">Auto</option><option value="melody">Melody</option><option value="accompaniment">Accompaniment</option></select></label><label className="check-label"><input type="checkbox" checked={protectedSet.has(review.id)} onChange={e=>setGuidance({...guidance,protectedNoteIds:e.target.checked?[...guidance.protectedNoteIds,review.id]:guidance.protectedNoteIds.filter(id=>id!==review.id)})}/>Protect this melody note</label><div className="button-row"><button className="secondary" onClick={()=>onSeek(review.start)}>Listen here</button><button className="secondary" onClick={()=>{setOpen(false);onCorrect(review.id)}}>Correct source pitch, timing or hand</button></div></div>}
    <div className="field-row"><label>Passage start (seconds)<input type="number" min="0" max={piece.duration} step=".1" value={start} onChange={e=>setStart(+e.target.value)}/></label><label>Passage end (seconds)<input type="number" min={start} max={piece.duration} step=".1" value={end} onChange={e=>setEnd(+e.target.value)}/></label><button className="secondary" onClick={()=>{setStart(loopA);setEnd(loopB)}}>Use loop range</button></div>
    <button className="secondary" disabled={end<=start} onClick={()=>{const ids=passage.filter(n=>guidance.roles[n.id]==='melody'||protectedSet.has(n.id)||(guidance.roles[n.id]!=='accompaniment'&&suggestedMelody.has(n.id))).map(n=>n.id);if(!ids.length){setError('Generate an arrangement or mark melody notes first, then protect this passage.');return}setGuidance({...guidance,protectedNoteIds:[...new Set([...guidance.protectedNoteIds,...ids])]})}}>Protect melody in this passage</button>
    <details><summary>Protected notes ({guidance.protectedNoteIds.length})</summary>{guidance.protectedNoteIds.map(id=>{const n=sourceNotes.find(n=>n.id===id);return <label className="check-label" key={id}><input type="checkbox" checked onChange={()=>setGuidance({...guidance,protectedNoteIds:guidance.protectedNoteIds.filter(x=>x!==id)})}/>{n?`${noteName(n.pitch)} · ${stamp(n.start)}`:`${id} · no longer available`}</label>})}</details>
    <button className="primary" disabled={busy||!online||!list} onClick={()=>void saveGuidance()}>Save melody guidance</button>
   </section>
   {!online&&<p className="notice">Connect to the server to generate and save arrangements.</p>}{error&&<p className="notice error" role="alert">{error}</p>}
   </div>
  </section></div>}
 </section>
}
