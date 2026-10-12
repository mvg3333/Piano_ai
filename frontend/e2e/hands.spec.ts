import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

test('accompaniment middle C uses the left staff and manual hand corrections survive regeneration',async({page,request})=>{
 test.setTimeout(90000)
 const root=path.resolve('..')
 const piece=JSON.parse(fs.readFileSync('public/demo.json','utf8'))
 piece.id='hand-context-test';piece.title='Contextual hand assignment verification'
 piece.source={kind:'upload',mediaClip:false}
 piece.raw.provenance={kind:'transcription',model:'Browser fixture'}
 piece.raw.pedals=[];piece.raw.tempos=[];piece.raw.duration=8
 piece.settings={tempo:120,numerator:4,denominator:4,quantization:'1/16',downbeat:0,useMidiTempo:false,cleanup:'off'}
 piece.duration=8;piece.edits=[]
 piece.raw.notes=[]
 // Repeated E3-A3-C4 accompaniment continues when a separate high melody enters.
 // Raw labels deliberately retain the old middle-C cutoff so the browser checks
 // effective assignment and immutable source data, not preassigned fixture hands.
 for(let phrase=0;phrase<4;phrase++){
  for(const [step,pitch] of [52,57,60].entries()){
   piece.raw.notes.push({id:`accompaniment-${phrase}-${pitch}`,pitch,start:.25+phrase*1.5+step*.4,end:1.6+phrase*1.5,velocity:75,hand:pitch<60?'left':'right'})
  }
 }
 for(const [i,pitch] of [74,77,86,77,74,77].entries()){
  piece.raw.notes.push({id:`treble-${i}`,pitch,start:3.3+i*.45,end:3.65+i*.45,velocity:80,hand:'right'})
 }
 piece.raw.notes.sort((a:{start:number;pitch:number},b:{start:number;pitch:number})=>a.start-b.start||a.pitch-b.pitch)
 piece.notes=piece.raw.notes
 const raw=structuredClone(piece.raw)
 const middleC='accompaniment-2-60'
 execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-c',
  "import json,sys; from backend import store; from backend.domain import apply_revision; p=json.load(sys.stdin); store.setup(); store.piece_save(apply_revision(p,p['settings'],[]))"],
  {cwd:root,env:{...process.env,PIANO_DATA_DIR:path.join(root,'data/browser-tests')},input:JSON.stringify(piece),timeout:30000})
 const saved=await (await request.get('/api/pieces/'+piece.id)).json()
 expect(saved.raw).toEqual(raw)
 expect(saved.notes.find((n:{id:string})=>n.id===middleC).hand).toBe('left')
 const leftFragment=saved.score.fragments.find((f:{noteId:string})=>f.noteId===middleC)
 expect(leftFragment.hand).toBe('left')
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/')
 await page.getByRole('button',{name:'My pieces',exact:true}).click()
 await page.locator(`[data-piece-id="${piece.id}"] .library-piece`).click()
 await expect(page.getByRole('heading',{name:piece.title,exact:true})).toBeVisible()
 const notehead=page.locator(`[data-performance-notes="${middleC}"]`).first()
 await expect(notehead).toBeAttached({timeout:20000})
 await expect(notehead.locator('path').first()).toHaveCSS('fill','rgb(13, 148, 136)')
 const engraved=await page.evaluate(({xml,id})=>{
  const note=new DOMParser().parseFromString(xml,'application/xml').querySelector(`note[id="${id}"]`)
  return {staff:note?.querySelector('staff')?.textContent,color:note?.getAttribute('color')?.toLowerCase()}
 },{xml:saved.score.musicxml,id:leftFragment.xmlId})
 expect(engraved).toEqual({staff:'2',color:'#0d9488'})
 await page.getByRole('button',{name:'Practice settings',exact:true}).click()
 await page.getByRole('combobox',{name:'Choose a note to correct'}).selectOption(middleC)
 const editor=page.getByRole('dialog',{name:'Correct note',exact:true})
 await expect(editor.getByRole('combobox',{name:'Hand',exact:true})).toHaveValue('left')
 await editor.getByRole('combobox',{name:'Hand',exact:true}).selectOption('right')
 await editor.getByRole('button',{name:'Save correction',exact:true}).click()
 await expect(editor).toHaveCount(0)
 await expect(notehead.locator('path').first()).toHaveCSS('fill','rgb(180, 83, 208)',{timeout:20000})
 await page.getByRole('button',{name:'Practice settings',exact:true}).click()
 await page.getByRole('spinbutton',{name:'Tempo (BPM)'}).fill('110')
 await page.getByRole('button',{name:'Regenerate & save score',exact:true}).click()
 await expect(page.getByRole('button',{name:'Regenerate & save score',exact:true})).toBeEnabled({timeout:20000})
 const corrected=await (await request.get('/api/pieces/'+piece.id)).json()
 expect(corrected.notes.find((n:{id:string})=>n.id===middleC).hand).toBe('right')
 expect(corrected.score.fragments.filter((f:{noteId:string})=>f.noteId===middleC).every((f:{hand:string})=>f.hand==='right')).toBe(true)
 expect(corrected.edits.find((n:{id:string})=>n.id===middleC).hand).toBe('right')
 expect(corrected.raw).toEqual(raw)
 await page.getByRole('combobox',{name:'Choose a note to correct'}).selectOption(middleC)
 await expect(editor.getByRole('combobox',{name:'Hand',exact:true})).toHaveValue('right')
 expect(errors).toEqual([])
})
