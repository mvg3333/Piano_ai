import {useEffect,useLayoutEffect,useRef,useState} from 'react'
import {Play,Pause,RotateCcw,Plus,Library,Settings2,Music2,Rows3,PanelTop,Repeat2,Volume2,ChevronDown,X,Upload,Link2,FileMusic,ArrowRight,Check,Maximize,Minimize,Download,Undo2,Trash2,LoaderCircle,Sun,Headphones,KeyboardMusic,ChevronLeft} from 'lucide-react'
import type {Piece,Note,Source,Job,Settings,Mode,Arrangement} from './types'
import {Playback} from './playback'
import type {ExternalClock} from './playback'
import {PianoRoll} from './PianoRoll'
import {ScoreView} from './ScoreView'
import {printScore} from './printScore'
import {YouTubePlayer} from './YouTubePlayer'
import {DraftOptions} from './DraftOptions'
import {ArrangementControls,difficultyLabel} from './ArrangementControls'
import {api,jsonPost,loadPiece,revisePiece,createJob,retranscribePiece} from './api'
import {noteName,songRange,secondsToBeats} from './timing'

const clock=(seconds:number)=>`${Math.floor(Math.max(0,seconds)/60)}:${String(Math.floor(Math.max(0,seconds)%60)).padStart(2,'0')}`
const errorText=(error:unknown)=>error instanceof Error?error.message:String(error)
type Dialog='new'|'library'|'settings'|'library-options'|'delete'|null
type LibraryPiece={id:string;title:string;created:number}

export default function App(){
 const [piece,setPiece]=useState<Piece>(),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const [arrangement,setArrangement]=useState<Arrangement>(),[comparing,setComparing]=useState(false)
 const stageHost=useRef<HTMLDivElement>(null),transportHost=useRef<HTMLElement>(null)
 const [stageHeight,setStageHeight]=useState<number>()
 const [customHeight,setCustomHeight]=useState<number>()
 const [online,setOnline]=useState(false),[model,setModel]=useState(false),[dialog,setDialog]=useState<Dialog>(null)
 const [view,setView]=useState('combined'),[split,setSplit]=useState(48),[size,setSize]=useState(.85)
 const [labels,setLabels]=useState(true),[octaves,setOctaves]=useState(false),[zoom,setZoom]=useState(9),[fullRange,setFullRange]=useState(false)
 const [low,setLow]=useState(43),[high,setHigh]=useState(81),[focus,setFocus]=useState(false)
 const [time,setTime]=useState(0),[playing,setPlaying]=useState(false),[busy,setBusy]=useState(false)
 const [speed,setSpeed]=useState(1),[hands,setHands]=useState('both'),[transpose,setTranspose]=useState(0),[mode,setMode]=useState<Mode>('synth')
 const [rates,setRates]=useState([.25,.5,.75,1,1.25,1.5,2]),[externalReady,setExternalReady]=useState(false)
 const [loop,setLoop]=useState(false),[loopA,setLoopA]=useState(0),[loopB,setLoopB]=useState(40)
 const [metronome,setMetronome]=useState(false),[countIn,setCountIn]=useState(false),[offset,setOffset]=useState(0)
 const [selection,setSelection]=useState<Note>(),[settings,setSettings]=useState<Settings>(),[undo,setUndo]=useState<{settings:Settings;edits:Note[]}[]>([])
 const [library,setLibrary]=useState<LibraryPiece[]>([])
 const [libraryTarget,setLibraryTarget]=useState<Piece>(),[librarySettings,setLibrarySettings]=useState<Settings>()
 const [deleteTarget,setDeleteTarget]=useState<LibraryPiece>(),[libraryBusy,setLibraryBusy]=useState(false),[libraryNotice,setLibraryNotice]=useState('')
 const [entry,setEntry]=useState('youtube'),[url,setUrl]=useState(''),[source,setSource]=useState<Source>(),[start,setStart]=useState(0),[end,setEnd]=useState<number|null>(30)
 const [job,setJob]=useState<Job>(),[jobNow,setJobNow]=useState(Date.now()),[fileBusy,setFileBusy]=useState(false)
 const [libraryJobTarget,setLibraryJobTarget]=useState<string>()
 const [wake,setWake]=useState(false),[printing,setPrinting]=useState(false)
 async function exportPdf(){
  if(!piece||!practice?.score.musicxml||printing)return
  player.pause();setPrinting(true);setError('')
  try{await printScore(practice.score.musicxml,piece.title+(arrangement?' - '+activeDifficulty:''),mode==='synth'?transpose:0)}
  catch(e){setError(errorText(e))}finally{setPrinting(false)}
 }
 const audio=useRef<HTMLAudioElement>(null),inputFile=useRef<HTMLInputElement>(null),playerRef=useRef<Playback|null>(null),demo=useRef<Piece|undefined>(undefined)
 if(!playerRef.current)playerRef.current=new Playback()
 const player=playerRef.current
 const latestPiece=useRef(piece);latestPiece.current=piece
 const selectedRef=useRef(arrangement);selectedRef.current=arrangement
 const practice=piece&&(arrangement?(comparing?arrangement.sourcePerformance:arrangement.performance):piece)
 const activeDifficulty=arrangement?(comparing?'Full transcription · comparison':difficultyLabel(arrangement.settings)):'Full transcription'
 function selectArrangement(next?:Arrangement){
  if(next&&next.pieceId!==latestPiece.current?.id)return
  setArrangement(next);setComparing(false)
  const view=next?.performance??latestPiece.current
  if(view){player.replacePerformance(view);const [lo,hi]=songRange(view.notes);setLow(lo);setHigh(hi)}
 }
 function compareArrangement(full:boolean){
  if(!arrangement)return
  setComparing(full);setMode('synth');setExternalReady(true);setRates([.25,.5,.75,1,1.25,1.5,2])
  const view=full?arrangement.sourcePerformance:arrangement.performance
  player.replacePerformance(view,true);const [lo,hi]=songRange(view.notes);setLow(lo);setHigh(hi)
 }
 function correctSource(id:string){const n=piece?.notes.find(n=>n.id===id);if(n){player.pause();setSelection({...n})}else setNotice('This source note is no longer available. The saved arrangement is unchanged.')}

 const openPiece=(next:Piece)=>{setArrangement(undefined);setComparing(false);player.setPiece(next);player.configureMode('synth');setMode('synth');setRates([.25,.5,.75,1,1.25,1.5,2]);setPiece(next);setSettings(next.settings);const [lo,hi]=songRange(next.notes);setLow(lo);setHigh(hi);setLoopA(0);setLoopB(next.duration);setLoop(false);setTime(0);setDialog(null);setSelection(undefined);setUndo([]);setNotice('');setError('');setTranspose(0);player.transpose=0;setSpeed(1);player.speed=1;setOffset(0);player.offset=0}
 useEffect(()=>{
  let alive=true
  player.onChange=()=>{if(alive){setPlaying(player.playing);setTime(player.time())}}
  void fetch('/demo.json').then(r=>r.json()).then(async p=>{try{p=await loadPiece('demo')}catch{/* Bundled demo works offline. */}demo.current=p;if(alive)openPiece(p)}).catch(e=>setError('Could not load the bundled demo: '+errorText(e)))
  const check=()=>api<{model:boolean}>('/health').then(h=>{if(alive){setOnline(true);setModel(h.model)}}).catch(()=>{if(alive)setOnline(false)})
  void check();const healthTimer=setInterval(check,20000)
  const uiTimer=setInterval(()=>{setTime(player.time());setPlaying(player.playing);setJobNow(Date.now())},70)
  const visibility=()=>{if(document.hidden&&player.playing){player.pause();setNotice('Playback paused while the app was in the background.')}}
  document.addEventListener('visibilitychange',visibility)
  return()=>{alive=false;clearInterval(healthTimer);clearInterval(uiTimer);document.removeEventListener('visibilitychange',visibility);player.pause()}
 // Initialization is deliberately one per mounted application.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[])
 useEffect(()=>{
  if(!job||!['queued','running'].includes(job.status))return
  let stopped=false,polling=false
  const poll=async()=>{
   if(stopped||polling)return
   polling=true
   try{
    const next=await api<Job>('/jobs/'+job.id)
    if(stopped)return
    if(next.status==='completed'&&next.piece_id){
     const result=await loadPiece(next.piece_id)
     if(stopped)return
     openPiece(result);setNotice('Transcription saved. Review the draft and make it yours.')
    }
    // Changing status disposes this effect, so finish loading the result first.
    setJob(next)
   }catch(e){if(!stopped)setError(errorText(e))}finally{polling=false}
  }
  const timer=setInterval(()=>void poll(),1000)
  return()=>{stopped=true;clearInterval(timer)}
 },[job?.id,job?.status])
 useEffect(()=>{let cancelled=false;if(dialog==='library'&&online)void api<LibraryPiece[]>('/pieces').then(list=>{if(!cancelled)setLibrary(list)}).catch(e=>{if(!cancelled)setError(errorText(e))});return()=>{cancelled=true}},[dialog,online])
 useEffect(()=>{
  if(!wake||!playing||!('wakeLock' in navigator))return
  let lock:WakeLockSentinel|undefined,stopped=false
  void navigator.wakeLock.request('screen').then(l=>{if(stopped)void l.release();else lock=l}).catch(()=>setNotice('Screen wake is unavailable here. Your device’s screen settings still apply.'))
  return()=>{stopped=true;void lock?.release()}
 },[wake,playing])
 useEffect(()=>{if(mode==='audio'&&audio.current){const el=audio.current;const external:ExternalClock={currentTime:()=>el.currentTime,play:()=>el.play(),pause:()=>el.pause(),seek:t=>{el.currentTime=t},rate:r=>{el.playbackRate=r;el.preservesPitch=true},isPlaying:()=>!el.paused&&el.readyState>=3};player.configureMode(mode,external);external.rate(speed);setExternalReady(true)}},[mode,piece?.id])

 async function togglePlay(){setError('');if(player.playing){player.pause();return}setBusy(true);try{await player.play()}catch(e){player.pause();setError(errorText(e))}finally{setBusy(false)}}
 function closeDialog(){if(libraryBusy)return;setError('');setDialog(dialog==='delete'||dialog==='library-options'?'library':null)}
 async function openLibraryOptions(id:string){
  setLibraryBusy(true);setError('');setLibraryNotice('')
  try{const target=await loadPiece(id);setLibraryTarget(target);setLibrarySettings({...target.settings});setDialog('library-options')}
  catch(e){setError(errorText(e))}finally{setLibraryBusy(false)}
 }
 async function regenerateLibraryPiece(){
  if(!libraryTarget||!librarySettings)return
  setLibraryBusy(true);setError('');setLibraryNotice('')
  if(latestPiece.current?.id===libraryTarget.id)player.pause()
  try{
   const next=await revisePiece(libraryTarget,librarySettings,libraryTarget.edits)
   setLibraryTarget(next);setLibrarySettings(next.settings)
   if(latestPiece.current?.id===next.id){setUndo(old=>[...old,{settings:libraryTarget.settings,edits:libraryTarget.edits}]);setPiece(next);setSettings(next.settings);if(!selectedRef.current)player.replacePerformance(next);setSelection(undefined);const [lo,hi]=songRange(next.notes);setLow(lo);setHigh(hi)}
   setLibraryNotice(`Saved changes to ${next.title}.`)
  }catch(e){setError(errorText(e))}finally{setLibraryBusy(false)}
 }
 async function retranscribeLibraryPiece(){
  if(!libraryTarget||!librarySettings||libraryBusy||working||!online||!model)return
  setLibraryBusy(true);setError('');setLibraryNotice('')
  try{
   const nextJob=await retranscribePiece(libraryTarget,librarySettings)
   setLibraryJobTarget(libraryTarget.id);setJob(nextJob)
  }catch(e){setError(errorText(e))}finally{setLibraryBusy(false)}
 }
 async function confirmDelete(){
  if(!deleteTarget)return
  setLibraryBusy(true);setError('')
  if(latestPiece.current?.id===deleteTarget.id)player.pause()
  try{
   const result=await api<{filesPending:boolean}>(`/pieces/${deleteTarget.id}`,{method:'DELETE'})
   setLibrary(list=>list.filter(p=>p.id!==deleteTarget.id))
   if(latestPiece.current?.id===deleteTarget.id&&demo.current)openPiece(demo.current)
   if(job?.piece_id===deleteTarget.id)setJob(undefined)
   setDeleteTarget(undefined);setLibraryTarget(undefined);setLibrarySettings(undefined)
   setLibraryNotice(result.filesPending?'Piece deleted. Remaining local files will be removed when the server restarts.':'Piece deleted.')
   setDialog('library')
  }catch(e){setError(errorText(e))}finally{setLibraryBusy(false)}
 }
 function chooseMode(value:Mode){player.configureMode(value);setMode(value);setExternalReady(value==='synth');setSpeed(1);player.speed=1;setRates(value==='youtube'?[1]:[.25,.5,.75,1,1.25,1.5,2])}
 function updateLoop(a:number,b:number,enabled=loop){a=Math.min(a,b-.1);b=Math.max(b,a+.1);setLoopA(a);setLoopB(b);setLoop(enabled);player.loopA=a;player.loopB=b;player.loop=enabled;player.seek(player.time())}
 async function applySettings(nextSettings:Settings,edits:Note[]){if(!piece)return;setBusy(true);setError('');player.pause();try{const next=await revisePiece(piece,nextSettings,edits);setUndo(old=>[...old,{settings:piece.settings,edits:piece.edits}]);setPiece(next);setSettings(next.settings);if(!selectedRef.current)player.replacePerformance(next);if(next.settings.cleanup!==piece.settings.cleanup){const [lo,hi]=songRange(next.notes);setLow(lo);setHigh(hi)}setSelection(undefined);setNotice('Changes saved. Original transcription preserved.')}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function undoRevision(){if(!piece||!undo.length)return;const previous=undo.at(-1)!;setBusy(true);setError('');player.pause();try{const next=await revisePiece(piece,previous.settings,previous.edits);setPiece(next);setSettings(next.settings);if(!selectedRef.current)player.replacePerformance(next);if(next.settings.cleanup!==piece.settings.cleanup){const [lo,hi]=songRange(next.notes);setLow(lo);setHigh(hi)}setUndo(list=>list.slice(0,-1));setSelection(undefined)}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function upload(file:File){setFileBusy(true);setError('');try{const data=new FormData();data.append('file',file);const suffix=source?.kind==='youtube'?`?youtubeReference=${source.id}`:'';const result=await api<Source&{piece?:Piece}>('/sources/upload'+suffix,{method:'POST',body:data});if(result.piece){openPiece(result.piece);setNotice('MIDI imported and saved.')}else{setSource(result);setStart(0);setEnd(Math.min(30,result.duration??30))}}catch(e){setError(errorText(e))}finally{setFileBusy(false)}}
 async function prepareYouTube(){setFileBusy(true);setError('');try{const s=await api<Source>('/sources/youtube',jsonPost({url}));setSource(s);setStart(s.suggestedStart??0);setEnd((s.suggestedStart??0)+30)}catch(e){setError(errorText(e))}finally{setFileBusy(false)}}
 async function transcribe(){if(!source)return;setError('');try{setJob(await createJob(source,start,end));setLibraryJobTarget(undefined)}catch(e){setError(errorText(e))}}
 async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else if(document.documentElement.requestFullscreen)await document.documentElement.requestFullscreen();else setNotice('Fullscreen is unavailable in this browser. Use your browser’s Add to Home Screen option.')}catch{setNotice('Fullscreen is unavailable in this browser.')}}
 const videoId=piece?.source.videoId??piece?.source.youtubeReference?.videoId
 const measure=practice?.score.measures.findLast(m=>m.startTime<=time)
 const isDemo=piece?.raw.provenance.kind==='demo'
 const working=job&&['queued','running'].includes(job.status)
 const jobCard=job&&<div className="job-card" role="status"><div><strong>{job.status==='completed'?'Ready to practice':job.stage.charAt(0).toUpperCase()+job.stage.slice(1)}</strong><span>{clock(((working?jobNow:job.updated*1000)-job.created*1000)/1000)} elapsed</span></div>{working&&<div className="indeterminate"/>}{job.error&&<p className="job-error">{job.error}</p>}<div className="button-row">{working&&<button className="secondary" onClick={()=>void api<Job>(`/jobs/${job.id}/cancel`,jsonPost({})).then(setJob).catch(e=>setError(errorText(e)))}>Cancel job</button>}{['failed','cancelled'].includes(job.status)&&<><button className="secondary" onClick={()=>void api<Job>(`/jobs/${job.id}/retry`,jsonPost({})).then(setJob).catch(e=>setError(errorText(e)))}>Retry</button>{dialog==='new'&&<button className="secondary" onClick={()=>setEntry('upload')}>Upload instead</button>}</>}</div><small>Stages report real work. The worker must be running to process queued jobs.</small></div>
 const range:[number,number]=fullRange?[21,108]:[low,high]
 useLayoutEffect(()=>{
  if(!piece)return
  const resize=()=>{
   const stage=stageHost.current,transport=transportHost.current
   if(stage&&transport){const footer=(document.querySelector('.practice-footer')?.getBoundingClientRect().height??0)+(document.querySelector('.practice-size')?.getBoundingClientRect().height??0);setStageHeight(Math.max(60,transport.getBoundingClientRect().top-(stage.getBoundingClientRect().top+window.scrollY)-footer-8))}
  }
  const observer=new ResizeObserver(resize)
  for(const el of document.querySelectorAll('.arrangement-bar,.active-difficulty,.app-header,.piece-heading,.practice-toolbar,.practice-size,.transport,.source-band,.workspace>.notice'))observer.observe(el)
  window.addEventListener('resize',resize);resize()
  return()=>{observer.disconnect();window.removeEventListener('resize',resize)}
 },[piece,mode,focus,notice,error,arrangement,comparing])
 if(!piece||!practice)return <div className="loading-page"><KeyboardMusic size={40}/><h1>Piano AI</h1><p>{error||'Opening your practice space…'}</p></div>

 return <div className={`app ${focus?'focus-mode':''}`}>
  <header className="app-header">
   <a className="brand" href="#" aria-label="Piano AI home" onClick={e=>{e.preventDefault();setDialog('library')}}><span className="brand-icon"><KeyboardMusic size={23}/></span><span>Piano<span className="brand-ai">AI</span></span></a>
   <span className="header-motto">A little practice, every day.</span>
   <div className="header-actions"><button className="compact-settings icon-button" aria-label="Practice settings" onClick={()=>setDialog('settings')}><Settings2 size={18}/></button><button className="quiet" aria-label="My pieces" onClick={()=>setDialog('library')}><Library size={17}/><span>My pieces</span></button><button className="primary small" onClick={()=>setDialog('new')}><Plus size={17}/><span>New piece</span></button></div>
  </header>
  <main className="workspace">
   <section className="piece-heading">
    <div className="piece-titles"><div className="eyebrow"><span className="status-dot"/>{isDemo?'YOUR PRACTICE SPACE':'SAVED TO YOUR LIBRARY'}<span className="tag">{isDemo?'ORIGINAL DEMO':'DRAFT SCORE'}</span></div><h1>{piece.title}</h1><div className="piece-meta"><span>{isDemo?'An original piano study':piece.source.kind==='midi'?'MIDI import':'Audio transcription'}</span><span className="dot">·</span><span>{Math.round(piece.settings.tempo)} BPM</span><span className="dot">·</span><span>{piece.settings.numerator}/{piece.settings.denominator}</span><span className="dot">·</span><span>{clock(piece.duration)}</span></div></div>
    <div className="heading-actions"><button className="secondary" aria-label="Print / Save PDF" title="Print / Save PDF (landscape)" disabled={!practice.score.musicxml||printing} onClick={()=>void exportPdf()}><Download size={17}/><span>{printing?'Preparing?':'Print / Save PDF'}</span></button><button className="quiet icon-button" title="Distraction-free practice" aria-label="Distraction-free practice" onClick={()=>setFocus(!focus)}>{focus?<Minimize size={19}/>:<Maximize size={19}/>}</button><button className="secondary" onClick={()=>setDialog('settings')}><Settings2 size={17}/><span>Practice settings</span></button></div>
   </section>
   {(error||notice)&&<div role={error?'alert':'status'} className={`notice ${error?'error':''}`}><span>{error||notice}</span><button className="icon-button" aria-label="Dismiss message" onClick={()=>{setError('');setNotice('')}}><X size={15}/></button></div>}
    <ArrangementControls key={piece.id} piece={piece} online={online} selected={arrangement} comparing={comparing} loopA={loopA} loopB={loopB} onChange={selectArrangement} onCompare={compareArrangement} onSeek={t=>player.seek(t)} onCorrect={correctSource} onSourceUpdated={next=>{if(next.id===latestPiece.current?.id)setPiece(next)}}/>
    <div className="active-difficulty" aria-label="Active difficulty">{activeDifficulty}</div>
    {arrangement&&mode!=='synth'&&<p className="notice arrangement-audio-notice">Original audio contains the full performance; the displayed arrangement is simplified.</p>}
   <section className="practice-card">
    <div className="practice-toolbar"><div className="view-tabs" role="group" aria-label="Practice view">{[{id:'score',label:'Score',icon:Music2},{id:'falling',label:'Falling notes',icon:Rows3},{id:'combined',label:'Combined',icon:PanelTop}].map(({id,label,icon:Icon})=><button key={id} aria-pressed={view===id} className={view===id?'selected':''} onClick={()=>setView(id)}><Icon size={15}/><span>{label}</span></button>)}</div><div className="toolbar-right"><button className="quiet expand-practice" aria-pressed={focus} onClick={()=>{setFocus(!focus);window.scrollTo(0,0)}}>{focus?<Minimize size={16}/>:<Maximize size={16}/>}<span>{focus?'Restore size':'Expand practice'}</span></button><span className="hand-legend"><i className="left-dot"/>Left<span/><i className="right-dot"/>Right</span><button className="quiet icon-button" title="Fullscreen" aria-label="Fullscreen" onClick={()=>void fullscreen()}><Maximize size={16}/></button></div></div>
    {mode==='youtube'&&videoId&&<div className="source-band"><YouTubePlayer videoId={videoId} clipStart={piece.clipStart} onError={setError} onState={state=>{if(state===1)player.followExternal(true);else if(state===0||state===2)player.followExternal(false)}} onRate={r=>{setSpeed(r);player.speed=r}} onReady={(external,available)=>{player.configureMode('youtube',external);setRates(available);setExternalReady(true)}}/><div><span className="eyebrow">ORIGINAL PERFORMANCE</span><p>Following the video’s clock.</p><small>Hand selection and transposition apply to synthesized piano only.</small></div></div>}
    <div ref={stageHost} className={`practice-stage ${view}`} style={{height:focus?stageHeight:customHeight??stageHeight,minHeight:0,maxHeight:'none'}}>
     {view!=='falling'&&<div className="score-panel" style={{flex:view==='combined'?`0 0 ${split}%`:'1'}}><div className="panel-caption"><span><Music2 size={13}/>SHEET MUSIC</span><span>{measure?`Measure ${measure.number}`:'Ready to practice'} <span className="caption-hint">· tap a measure to seek</span></span></div><ScoreView piece={practice} player={player} size={size} transpose={mode==='synth'?transpose:0} onSeek={t=>player.seek(t)}/></div>}
     {view==='combined'&&<div className="split-divider"><input aria-label="Score and falling notes split" type="range" min="25" max="70" value={split} onChange={e=>setSplit(+e.target.value)}/><span/></div>}
     {view!=='score'&&<div className="roll-panel"><div className="roll-caption"><span>FOLLOW THE NOTES</span><span>{noteName(range[0])} — {noteName(range[1])}<span className="live-dot"/></span></div><PianoRoll piece={practice} player={player} range={range} labels={labels} octaves={octaves} zoom={zoom} onSelect={n=>correctSource(n.id)}/></div>}
    </div>
    {!focus&&<div className="practice-size"><label>Panel height <input aria-label="Practice panel height" type="range" min="240" max="1400" step="10" value={customHeight??Math.max(240,Math.min(1400,Math.round((stageHeight??400)/10)*10))} onChange={e=>setCustomHeight(+e.target.value)}/></label><button className="quiet" onClick={()=>setCustomHeight(undefined)} disabled={customHeight===undefined}>Auto fit</button></div>}
    <div className="practice-footer"><span><Headphones size={14}/>{isDemo?'Original demo · ready when you are':'Estimated hands · tap a falling note to correct it'}</span><span>{online?'Saved on this computer':'Demo available · server offline'}</span></div>
   </section>
   <div className="under-card"><span><Sun size={14}/> Find a comfortable tempo. Let your hands catch up.</span><span>Follow along on your piano · no listening or grading</span></div>
  </main>

  <footer ref={transportHost} className="transport">
   <div className="timeline"><span>{clock(time)}</span><input aria-label="Playback position" type="range" min="0" max={practice.duration} step="0.01" value={Math.min(time,practice.duration)} onChange={e=>player.seek(+e.target.value)}/><span>{clock(practice.duration)}</span></div>
   {loop&&<div className="loop-controls"><label>A <input aria-label="Loop start" type="range" min="0" max={practice.duration} step=".1" value={loopA} onChange={e=>updateLoop(Math.min(+e.target.value,loopB-.1),loopB)}/><b>{clock(loopA)}</b></label><label>B <input aria-label="Loop end" type="range" min="0" max={practice.duration} step=".1" value={loopB} onChange={e=>updateLoop(loopA,Math.max(+e.target.value,loopA+.1))}/><b>{clock(loopB)}</b></label></div>}
   <div className="transport-row"><div className="play-controls"><button className="quiet icon-button" aria-label="Restart" title="Restart" onClick={()=>player.seek(loop?loopA:0)}><RotateCcw size={19}/></button><button className="play-button" aria-label={playing?'Pause':'Play'} disabled={busy||(mode!=='synth'&&!externalReady)} onClick={()=>void togglePlay()}>{busy?<LoaderCircle className="spin" size={23}/>:playing?<Pause size={23} fill="currentColor"/>:<Play size={23} fill="currentColor"/>}</button><div className="playing-label"><strong>{player.countEnd?'Count in…':playing?'Keep going.':'Take your time.'}</strong><small>{mode==='synth'?activeDifficulty:mode==='youtube'?'YouTube playback':'Original audio'}</small></div></div>
    <div className="transport-options"><label className="speed-control"><span className="control-caption">SPEED</span><select aria-label="Playback speed" value={speed} onChange={e=>{const s=+e.target.value;setSpeed(s);player.rate(s)}}>{rates.map(r=><option key={r} value={r}>{r}×</option>)}</select></label><button className={`loop-button ${loop?'enabled':''}`} aria-label="Toggle loop" aria-pressed={loop} onClick={()=>updateLoop(loopA,loopB,!loop)}><Repeat2 size={19}/><span>Loop</span></button><div className="hand-buttons" role="group" aria-label="Synthesized hands">{['left','both','right'].map(h=><button key={h} disabled={mode!=='synth'} className={hands===h?'active':''} aria-pressed={hands===h} onClick={()=>{setHands(h);player.setHands(h)}}>{h==='both'?'Both hands':h==='left'?'L':'R'}</button>)}</div><label className="sound-control"><Volume2 size={17}/><select aria-label="Playback source" value={mode} onChange={e=>chooseMode(e.target.value as Mode)}><option value="synth">Piano</option>{piece.source.mediaClip&&<option value="audio">Original audio</option>}{videoId&&<option value="youtube">YouTube video</option>}</select><ChevronDown size={12}/></label></div>
   </div>
  </footer>
  {mode==='audio'&&<audio ref={audio} src={`/api/pieces/${piece.id}/media`} preload="auto" onEnded={()=>player.pause()} onError={()=>setError('Original audio is unavailable. Reconnect to the server or choose Piano playback.')}/>}

  {dialog&&<div className="modal-backdrop" onClick={closeDialog}><section key={dialog} className={`modal ${dialog==='settings'?'settings-modal':''}`} role={dialog==='delete'?'alertdialog':'dialog'} aria-modal="true" aria-label={dialog==='new'?'New piece':dialog==='library'?'My pieces':dialog==='library-options'?'Cleanup and score options':dialog==='delete'?'Delete piece':'Practice settings'} onClick={e=>e.stopPropagation()}>
   <header className="modal-header"><div><span className="eyebrow">PIANO AI</span><h2>{dialog==='new'?'Your next piece starts here.':dialog==='library'?'A little repertoire.':dialog==='library-options'?'Clean up & regenerate':dialog==='delete'?'Delete this piece?':'Make room for your rhythm.'}</h2></div><button className="icon-button" disabled={libraryBusy} aria-label="Close dialog" onClick={closeDialog}><X size={21}/></button></header>
   {error&&<div className="notice error" role="alert">{error}</div>}
   {dialog==='new'&&<>
    <p className="muted">Bring a recording, or import MIDI for notes that are ready to play.</p><div className="entry-tabs">{[{id:'youtube',label:'YouTube',icon:Link2},{id:'upload',label:'Audio / video',icon:Upload},{id:'midi',label:'MIDI',icon:FileMusic}].map(({id,label,icon:Icon})=><button className={entry===id?'selected':''} key={id} onClick={()=>setEntry(id)}><Icon size={17}/>{label}</button>)}</div>
    {!online&&<div className="notice">Start the Piano AI server to import or transcribe. The bundled demo is ready now.</div>}
    {entry==='youtube'?<div className="youtube-input"><label>YouTube performance URL<input type="url" placeholder="https://www.youtube.com/watch?v=…" value={url} onChange={e=>setUrl(e.target.value)}/></label><button className="primary" disabled={!online||!url||fileBusy} onClick={()=>void prepareYouTube()}>Use link <ArrowRight size={17}/></button><small>Public piano performances work best. If audio acquisition fails, upload a file and keep this video reference.</small></div>:<button className="upload-zone" disabled={!online||fileBusy} onClick={()=>inputFile.current?.click()}>{fileBusy?<LoaderCircle className="spin" size={30}/>:entry==='midi'?<FileMusic size={32}/>:<Upload size={32}/>}<strong>{fileBusy?'Reading your file…':entry==='midi'?'Choose a MIDI file':'Choose an audio or video file'}</strong><span>{entry==='midi'?'MID, MIDI · no transcription needed':'WAV, MP3, FLAC, OGG, M4A, AAC, MP4, WebM · up to 500 MiB'}</span></button>}
    <input ref={inputFile} type="file" hidden accept={entry==='midi'?'.mid,.midi':'.wav,.mp3,.flac,.ogg,.m4a,.aac,.mp4,.webm'} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value=''}}/>
    {source&&<div className="source-preview"><div className="source-title"><Check size={18}/><strong>{source.title}</strong></div><p className="muted">Try a short interval first. Times are in seconds from the original recording.</p><div className="field-row"><label>Start<input type="number" min="0" step=".1" value={start} onChange={e=>setStart(+e.target.value)}/></label><label>End<input type="number" min={start+.1} step=".1" placeholder="To the end" value={end??''} onChange={e=>setEnd(e.target.value?+e.target.value:null)}/></label><button className="secondary" onClick={()=>{setStart(0);setEnd(null)}}>Whole piece</button></div>{!model&&<p className="notice">The model environment is not installed. Run the model setup first; MIDI import remains available.</p>}<button className="primary wide" disabled={!!working||!online||!model} onClick={()=>void transcribe()}>{working?<LoaderCircle className="spin" size={18}/>:<Music2 size={18}/>}Transcribe piano</button></div>}
    {jobCard}
    <p className="fine-print">Solo piano is the initial target. Reverb, dense accompaniment and sustain can reduce transcription accuracy. No microphone listening or grading.</p>
   </>}
   {dialog==='library'&&<>
    <p className="muted">Open a piece to practice, or adjust its cleanup and score options here.</p>
    {libraryNotice&&<p className="notice" role="status">{libraryNotice}</p>}
    {libraryBusy&&<p className="muted" role="status">Loading piece options...</p>}
    <button className="library-piece" disabled={libraryBusy} onClick={()=>{if(demo.current)openPiece(demo.current)}}><span className="piece-icon"><Music2/></span><span><strong>Windowlight</strong><small>Original demo · 0:40 · always available</small></span><ArrowRight size={18}/></button>
    {library.filter(p=>p.id!=='demo').map(p=><div className="library-entry" key={p.id} data-piece-id={p.id}>
     <button className="library-piece" disabled={!online||libraryBusy} onClick={()=>void loadPiece(p.id).then(openPiece).catch(e=>setError(errorText(e)))}><span className="piece-icon"><FileMusic/></span><span><strong>{p.title}</strong><small>{new Date(p.created*1000).toLocaleDateString()} · saved piece</small></span><ArrowRight size={18}/></button>
     <div className="library-actions">
      <button className="secondary" disabled={!online||libraryBusy} aria-label={`Cleanup and regenerate ${p.title}`} onClick={()=>void openLibraryOptions(p.id)}><Settings2 size={16}/>Cleanup & regenerate</button>
      <button className="quiet danger" disabled={!online||libraryBusy} aria-label={`Delete ${p.title}`} onClick={()=>{setDeleteTarget(p);setError('');setLibraryNotice('');setDialog('delete')}}><Trash2 size={16}/>Delete</button>
     </div>
    </div>)}
    {!online&&<p className="notice">Connect to the server to manage your saved pieces.</p>}
    <button className="primary wide" disabled={libraryBusy} onClick={()=>setDialog('new')}><Plus size={18}/>Add a piece</button>
   </>}
   {dialog==='library-options'&&libraryTarget&&librarySettings&&<>
    <p className="library-target-title">{libraryTarget.title}</p>
    <p className="muted">Apply cleanup and score options to the existing notes. Your original notes and manual corrections are preserved. Regenerating the score does not analyze the audio again.</p>
    {libraryNotice&&<p className="notice" role="status">{libraryNotice}</p>}
    {!online&&<p className="notice">Connect to the server to save changes.</p>}
    <div className="settings-content"><DraftOptions piece={libraryTarget} settings={librarySettings} onChange={setLibrarySettings} onApply={()=>void regenerateLibraryPiece()} busy={libraryBusy} online={online} combinedAction/>
     {libraryTarget.source.mediaClip&&!['midi','demo'].includes(libraryTarget.source.kind)&&<section>
      <h3>Listen again for the notes</h3>
      <p className="muted">Analyze the saved recording again with the piano transcription model, using the cleanup and score options above. This creates a new copy. Your current piece and its manual corrections stay in the original copy.</p>
      {!model&&online&&<p className="notice">Install the transcription model to analyze the audio again.</p>}
      <button className="secondary" disabled={!online||!model||libraryBusy||!!working} onClick={()=>void retranscribeLibraryPiece()}>{working?<LoaderCircle className="spin" size={17}/>:<Music2 size={17}/>}Re-transcribe audio</button>
     </section>}
    </div>
    {libraryJobTarget===libraryTarget.id&&jobCard}
    <div className="button-row"><button className="secondary" disabled={libraryBusy} onClick={closeDialog}><ChevronLeft size={16}/>Back to My pieces</button></div>
   </>}
   {dialog==='delete'&&deleteTarget&&<>
    <p className="library-target-title">{deleteTarget.title}</p>
    <p className="muted">This permanently removes this saved piece, its note corrections, and its practice audio from this computer. This cannot be undone.</p>
    <div className="button-row"><button className="secondary" disabled={libraryBusy} onClick={closeDialog} autoFocus>Cancel</button><button className="primary delete-confirm" disabled={!online||libraryBusy} onClick={()=>void confirmDelete()}><Trash2 size={16}/>{libraryBusy?'Deleting...':'Delete piece'}</button></div>
   </>}
   {dialog==='settings'&&settings&&<div className="settings-content">
    <section><h3>Practice your way</h3><label className="settings-source">Playback source<select aria-label="Settings playback source" value={mode} onChange={e=>chooseMode(e.target.value as Mode)}><option value="synth">Synthesized piano</option>{piece.source.mediaClip&&<option value="audio">Original uploaded audio</option>}{videoId&&<option value="youtube">Original YouTube video</option>}</select></label><div className="toggle-row"><label><input type="checkbox" checked={countIn} onChange={e=>{setCountIn(e.target.checked);player.countIn=e.target.checked}}/>One-measure count-in</label><label><input type="checkbox" checked={metronome} onChange={e=>{setMetronome(e.target.checked);player.metronome=e.target.checked}}/>Metronome</label></div><div className="field-row"><label>Transpose (piano only)<input type="number" min="-24" max="24" disabled={mode!=='synth'} value={transpose} onChange={e=>{const n=Math.max(-24,Math.min(24,+e.target.value));setTranspose(n);player.setTranspose(n)}}/></label><label>Source sync offset (seconds)<input type="number" min="-30" max="30" step=".05" value={offset} onChange={e=>{const t=player.time();setOffset(+e.target.value);player.offset=+e.target.value;player.seek(t)}}/></label></div><small>Positive offset plays a later source time for the same displayed note.</small><div className="button-row"><button className="secondary" onClick={()=>updateLoop(Math.min(time,loopB-.1),loopB,true)}>Set A here · {clock(time)}</button><button className="secondary" onClick={()=>updateLoop(loopA,Math.max(time,loopA+.1),true)}>Set B here · {clock(time)}</button></div></section>
    <section><h3>Score & keyboard</h3><label className="slider-label">Notation size<input aria-label="Notation size" type="range" min=".5" max="1.5" step=".05" value={size} onChange={e=>setSize(+e.target.value)}/></label><label className="slider-label">Minimum key width<input aria-label="Keyboard zoom" type="range" min="6" max="36" value={zoom} onChange={e=>setZoom(+e.target.value)}/></label><div className="toggle-row"><label><input type="checkbox" checked={labels} onChange={e=>setLabels(e.target.checked)}/>Note names</label><label><input type="checkbox" checked={octaves} onChange={e=>setOctaves(e.target.checked)}/>Octave labels</label><label><input type="checkbox" checked={fullRange} onChange={e=>setFullRange(e.target.checked)}/>Full 88-key view</label></div><div className="field-row"><label>Lowest MIDI note<input type="number" min="21" max={high-1} value={low} onChange={e=>setLow(Math.max(21,Math.min(high-1,+e.target.value)))}/></label><label>Highest MIDI note<input type="number" min={low+1} max="108" value={high} onChange={e=>setHigh(Math.max(low+1,Math.min(108,+e.target.value)))}/></label><button className="secondary" onClick={()=>{const [l,h]=songRange(piece.notes);setLow(l);setHigh(h);setFullRange(false)}}>Fit to song</button></div></section>
    <DraftOptions piece={piece} settings={settings} onChange={setSettings} onApply={()=>void applySettings(settings,piece.edits)} busy={busy} online={online}/>
    <section><h3>Corrections & exports</h3><p className="muted">Tap a falling note to edit it, or choose one below. Exports use {arrangement?arrangement.name:'Full transcription'}; MIDI and MusicXML use the original pitch. PDF prints the displayed score, including its current transposition.</p><select aria-label="Choose a note to correct" value="" onChange={e=>{const n=piece.notes.find(n=>n.id===e.target.value);if(n){setSelection({...n});setDialog(null);player.pause()}}}><option value="">Choose a note…</option>{piece.notes.map(n=><option key={n.id} value={n.id}>{noteName(n.pitch)} · {n.start.toFixed(2)}s · {n.hand} hand</option>)}</select><div className="button-row"><button className="secondary" disabled={!online||!undo.length||busy} onClick={()=>void undoRevision()}><Undo2 size={16}/>Undo last change</button><button className="secondary" disabled={!online||!piece.edits.length||busy} onClick={()=>void applySettings(piece.settings,[])}>Reset note corrections</button></div><div className="button-row"><button className="secondary" disabled={!practice.score.musicxml||printing} onClick={()=>void exportPdf()}><Download size={16}/>{printing?'Preparing?':'Print / Save PDF'}</button><a className={`button secondary ${!online?'disabled':''}`} href={`/api/pieces/${piece.id}/export/midi${arrangement?`?arrangementId=${arrangement.id}`:''}`} download><Download size={16}/>MIDI</a><a className={`button secondary ${!online?'disabled':''}`} href={`/api/pieces/${piece.id}/export/musicxml${arrangement?`?arrangementId=${arrangement.id}`:''}`} download><Download size={16}/>MusicXML</a></div><label>Piece title<input maxLength={160} defaultValue={piece.title} onBlur={e=>{if(e.target.value.trim()&&e.target.value!==piece.title&&online)void api<Piece>(`/pieces/${piece.id}`,{...jsonPost({title:e.target.value}),method:'PATCH'}).then(setPiece).catch(e=>setError(errorText(e)))}}/></label></section>
    <section><h3>Device & offline</h3><label className="check-label"><input type="checkbox" checked={wake} onChange={e=>setWake(e.target.checked)}/>Keep the screen awake while playing</label><button className="secondary" onClick={()=>void fullscreen()}><Maximize size={16}/>Fullscreen</button><p className="fine-print">The app shell, piano samples, and original demo can be cached on HTTPS or localhost. Transcription and your saved library need the server. YouTube needs internet. Fullscreen, wake lock, and installation depend on your browser; ordinary Wi-Fi HTTP practice still works.</p><a href="/samples/ATTRIBUTION.txt" target="_blank" rel="noreferrer">Piano sample credits & license</a></section>
   </div>}
  </section></div>}
  {selection&&<div className="modal-backdrop" onClick={()=>setSelection(undefined)}><section role="dialog" aria-modal="true" aria-label="Correct note" className="modal note-modal" onClick={e=>e.stopPropagation()}><header className="modal-header"><div><span className="eyebrow">NOTE CORRECTION</span><h2>{noteName(selection.pitch)} <small>{selection.hand} hand</small></h2></div><button className="icon-button" aria-label="Close note editor" onClick={()=>setSelection(undefined)}><X/></button></header><div className="field-row"><label>MIDI pitch<input type="number" min="0" max="127" value={selection.pitch} onChange={e=>setSelection({...selection,pitch:+e.target.value})}/></label><label>Hand<select value={selection.hand} onChange={e=>setSelection({...selection,hand:e.target.value as Note['hand']})}><option value="left">Left</option><option value="right">Right</option></select></label></div><div className="field-row"><label>Onset (seconds)<input type="number" min="0" step=".01" value={selection.start} onChange={e=>setSelection({...selection,start:+e.target.value})}/></label><label>Duration (seconds)<input type="number" min=".01" step=".01" value={+(selection.end-selection.start).toFixed(3)} onChange={e=>setSelection({...selection,end:selection.start+ +e.target.value})}/></label></div><p className="muted">You are correcting the source transcription. Saved arrangements remain unchanged until refreshed. Original performance data is retained.</p><div className="button-row"><button className="primary" disabled={!online||busy} onClick={()=>void applySettings(piece.settings,[...piece.edits.filter(e=>e.id!==selection.id),selection])}>Save correction</button><button className="secondary danger" disabled={!online||busy} onClick={()=>void applySettings(piece.settings,[...piece.edits.filter(e=>e.id!==selection.id),{...selection,deleted:true}])}><Trash2 size={16}/>Delete note</button></div>{error&&<p className="notice error">{error}</p>}{!online&&<p className="notice">Connect to the server to save corrections.</p>}</section></div>}
  {focus&&<button className="exit-focus" onClick={()=>setFocus(false)}><ChevronLeft size={17}/>Exit focus</button>}
 </div>
}
