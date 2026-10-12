import type {Piece,Settings} from './types'

export function DraftOptions({piece,settings,onChange,onApply,busy,online,combinedAction=false}: {
 piece:Piece;settings:Settings;onChange:(settings:Settings)=>void;onApply:()=>void;
 busy:boolean;online:boolean;combinedAction?:boolean
}){
 return <>
  {piece.raw.provenance.kind==='transcription'&&<section>
   <h3>Reduce stray notes</h3>
   <p className="muted">Hide uncertain detections from the score, falling notes, piano playback, and exports. Quiet notes can also be hidden; choose Off to restore them. Your manual corrections take priority.</p>
   <label>Note cleanup<select aria-label="Note cleanup" disabled={busy} value={settings.cleanup??'off'} onChange={e=>onChange({...settings,cleanup:e.target.value as Settings['cleanup']})}>
    <option value="off">Off - all detected notes</option><option value="balanced">Balanced</option><option value="strong">Strong - fewer notes</option>
   </select></label>
   <p className="muted" data-testid="cleanup-summary">{piece.cleanup?.hiddenNoteIds.length??0} notes hidden · {piece.notes.length} retained</p>
   {!piece.noteEvidence&&<small>This older transcription uses note strength and duration only. Transcribe it again to also check note attacks.</small>}
   {!combinedAction&&<button className="primary" disabled={!online||busy} onClick={onApply}>{busy?'Updating...':'Apply cleanup'}</button>}
  </section>}
  <section>
   <h3>Shape the draft score</h3>
   <p className="muted">These settings change notation. Recorded note timing stays intact. Hands and rhythm are estimates.</p>
   {piece.raw.provenance.kind==='transcription'&&<p className="muted">Regenerating also estimates hands from nearby notes and chords. Your manual hand corrections take priority.</p>}
   <fieldset className="draft-fields" disabled={busy}>
    <div className="field-row">
     <label>Tempo (BPM)<input type="number" min="20" max="300" value={settings.tempo} onChange={e=>onChange({...settings,tempo:+e.target.value,useMidiTempo:false})}/></label>
     <label>Beats per bar<input type="number" min="1" max="12" value={settings.numerator} onChange={e=>onChange({...settings,numerator:+e.target.value})}/></label>
     <label>Beat unit<select value={settings.denominator} onChange={e=>onChange({...settings,denominator:+e.target.value})}>{[2,4,8,16].map(n=><option key={n}>{n}</option>)}</select></label>
    </div>
    <div className="field-row">
     <label>Quantization<select value={settings.quantization} onChange={e=>onChange({...settings,quantization:e.target.value})}>{['1/4','1/8','1/16','1/32','1/8T','1/16T'].map(q=><option key={q}>{q}</option>)}</select></label>
     <label>First downbeat (seconds)<input type="number" min="0" step=".01" value={settings.downbeat} onChange={e=>onChange({...settings,downbeat:+e.target.value})}/></label>
    </div>
    {piece.source.kind==='midi'&&<label className="check-label"><input type="checkbox" checked={settings.useMidiTempo} onChange={e=>onChange({...settings,useMidiTempo:e.target.checked})}/>Use imported MIDI tempo changes</label>}
   </fieldset>
   <button className="primary" disabled={!online||busy} onClick={onApply}>{busy?'Regenerating...':combinedAction?'Apply & regenerate':'Regenerate & save score'}</button>
  </section>
 </>
}
