import {test,expect} from '@playwright/test'
import fs from 'node:fs'

test('saved audio can be re-transcribed with selected options into a new copy',async({page})=>{
 const demo=JSON.parse(fs.readFileSync('public/demo.json','utf8'))
 const original=structuredClone(demo)
 original.id='rescan-original';original.title='Andrea Vanzo - Song Of Storms'
 original.source={kind:'youtube',videoId:'pMU3_1VbRn0',mediaClip:true}
 original.clipStart=12;original.raw.provenance.kind='transcription'
 const note=original.raw.notes[0]
 original.edits=[{...note,pitch:note.pitch+1}]
 original.settings={...original.settings,cleanup:'balanced'}
 const untouched=structuredClone(original)
 const midi={...structuredClone(original),id:'rescan-midi',title:'Imported MIDI',source:{kind:'midi'}}
 const copy={...structuredClone(original),id:'rescan-copy',title:original.title+' - New transcription',edits:[]}
 let modelAvailable=false,complete=false,requestCount=0
 let submitted:unknown
 const unexpectedWrites:string[]=[]
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 const job={id:'rescan-job',status:'queued',stage:'queued',created:Date.now()/1000,updated:Date.now()/1000}
 await page.route('**/api/health',route=>route.fulfill({json:{model:modelAvailable}}))
 await page.route('**/api/pieces',route=>route.fulfill({json:[original,midi,...(complete?[copy]:[])].map(p=>({id:p.id,title:p.title,created:job.created}))}))
 await page.route('**/api/pieces/rescan-*',route=>{
  if(route.request().method()!=='GET')unexpectedWrites.push(route.request().url())
  const id=route.request().url().split('/').at(-1)
  return route.fulfill({json:id===original.id?original:id===copy.id?copy:midi})
 })
 await page.route('**/api/pieces/rescan-original/transcriptions',route=>{
  requestCount++;submitted=route.request().postDataJSON()
  copy.settings=(submitted as {settings:typeof original.settings}).settings
  return route.fulfill({status:202,json:job})
 })
 await page.route('**/api/jobs/rescan-job',route=>route.fulfill({json:complete?{...job,status:'completed',stage:'completed',piece_id:copy.id}:job}))
 await page.goto('/')
 await page.getByRole('button',{name:'My pieces',exact:true}).click()
 await page.getByRole('button',{name:'Cleanup and regenerate '+original.title,exact:true}).click()
 const options=page.getByRole('dialog',{name:'Cleanup and score options',exact:true})
 const rescan=options.getByRole('button',{name:'Re-transcribe audio',exact:true})
 await expect(rescan).toBeDisabled()
 await expect(options.getByText('Install the transcription model to analyze the audio again.',{exact:true})).toBeVisible()
 modelAvailable=true
 await page.reload()
 await page.getByRole('button',{name:'My pieces',exact:true}).click()
 // MIDI has no audio to rescan; keep its cleanup/score workflow unchanged.
 await page.getByRole('button',{name:'Cleanup and regenerate '+midi.title,exact:true}).click()
 await expect(rescan).toHaveCount(0)
 await options.getByRole('button',{name:'Back to My pieces'}).click()
 await page.getByRole('button',{name:'Cleanup and regenerate '+original.title,exact:true}).click()
 await expect(rescan).toBeEnabled()
 await expect(options.getByText(/Your current piece and its manual corrections stay in the original copy/)).toBeVisible()
 await options.getByRole('combobox',{name:'Note cleanup'}).selectOption('off')
 await options.getByRole('spinbutton',{name:'Tempo (BPM)'}).fill('116')
 await options.getByRole('spinbutton',{name:'Beats per bar'}).fill('3')
 await options.getByRole('combobox',{name:'Quantization',exact:true}).selectOption('1/8T')
 await options.getByRole('spinbutton',{name:'First downbeat (seconds)'}).fill('0.3')
 await page.setViewportSize({width:390,height:844})
 await rescan.scrollIntoViewIfNeeded()
 await expect(options).toBeVisible()
 expect(await options.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true)
 await rescan.click()
 await expect(rescan).toBeDisabled()
 await expect(options.locator('.job-card')).toContainText('Queued')
 await expect(options.getByRole('button',{name:'Cancel job',exact:true})).toBeVisible()
 expect(submitted).toEqual({settings:{...original.settings,cleanup:'off',tempo:116,numerator:3,quantization:'1/8T',downbeat:.3,useMidiTempo:false}})
 expect(requestCount).toBe(1)
 expect(original).toEqual(untouched)
 expect(unexpectedWrites).toEqual([])
 await page.screenshot({path:'test-results/retranscription-mobile.png'})
 complete=true
 await expect(page.getByRole('heading',{name:copy.title,exact:true})).toBeVisible({timeout:10000})
 await expect(page.getByRole('dialog')).toHaveCount(0)
 await page.getByRole('button',{name:'My pieces',exact:true}).click()
 await expect(page.locator(`[data-piece-id="${original.id}"]`)).toBeVisible()
 await expect(page.locator(`[data-piece-id="${copy.id}"]`)).toBeVisible()
 expect(original).toEqual(untouched)
 expect(copy.edits).toEqual([])
 expect(errors).toEqual([])
})
