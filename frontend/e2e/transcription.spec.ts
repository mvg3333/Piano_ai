import {test,expect} from '@playwright/test'
import {execFileSync} from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

test('transcription score, cleanup, restore and saved exports',async({page,request})=>{
 test.setTimeout(120000)
 const root=path.resolve('..')
 const fixture=process.env.PIANO_TEST_PIECE
 const piece=JSON.parse(fs.readFileSync(fixture??path.resolve('public/demo.json'),'utf8'))
 if(!fixture){
  piece.raw.provenance.kind='transcription'
  piece.noteEvidence=Object.fromEntries(piece.raw.notes.map((n:{id:string},i:number)=>[n.id,{onset:i%3===0?.4:.95}]))
 }
 piece.title='Transcription cleanup verification'
 // Seed only the isolated browser-test database, never the user's library.
 execFileSync(path.join(root,'.venv/Scripts/python.exe'),['-c',
  "import json,sys; from backend import store; from backend.domain import apply_revision; p=json.load(sys.stdin); p['id']='cleanup-browser'; store.setup(); store.piece_save(apply_revision(p,{**p['settings'],'cleanup':'off'},p.get('edits',[])))"],
  {cwd:root,env:{...process.env,PIANO_DATA_DIR:path.join(root,'data/browser-tests')},input:JSON.stringify(piece),timeout:30000})
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('/')
 await page.getByRole('button',{name:'My pieces',exact:true}).click()
 await page.locator('.library-piece').filter({hasText:'Transcription cleanup verification'}).click()
 await expect(page.getByRole('heading',{name:'Transcription cleanup verification',exact:true})).toBeVisible()
 await expect(page.getByRole('slider',{name:'Playback position'})).toHaveAttribute('max',String(piece.duration))
 await expect(page.locator('.score-render svg').first()).toBeVisible({timeout:30000})
 await expect(page.locator('.score-empty')).toHaveCount(0)
 await page.getByRole('slider',{name:'Playback position'}).fill(String(Math.min(61,piece.duration/2)))
 await expect.poll(async()=>+(await page.locator('.score-render').getAttribute('data-cursor-beat')??0)).toBeGreaterThan(10)
 await expect(page.locator('[data-performance-notes]').first()).toBeAttached()
 await page.getByRole('button',{name:'Practice settings',exact:true}).click()
 await page.getByRole('combobox',{name:'Note cleanup'}).selectOption('balanced')
 await page.getByRole('button',{name:'Apply cleanup',exact:true}).click()
 await expect(page.getByRole('button',{name:'Apply cleanup',exact:true})).toBeEnabled({timeout:30000})
 const cleaned=await (await request.get('/api/pieces/cleanup-browser')).json()
 expect(cleaned.notes.length).toBeLessThan(piece.raw.notes.length)
 expect(cleaned.raw).toEqual(piece.raw)
 await expect(page.getByTestId('cleanup-summary')).toHaveText(`${cleaned.cleanup.hiddenNoteIds.length} notes hidden · ${cleaned.notes.length} retained`)
 expect((await request.get('/api/pieces/cleanup-browser/export/musicxml')).ok()).toBe(true)
 expect((await request.get('/api/pieces/cleanup-browser/export/midi')).ok()).toBe(true)
 await page.getByRole('button',{name:'Close dialog',exact:true}).click()
 await expect(page.locator('.score-render svg').first()).toBeVisible()
 await page.screenshot({path:'test-results/transcription-cleaned.png',fullPage:true})
 await page.getByRole('button',{name:'Practice settings',exact:true}).click()
 await page.getByRole('combobox',{name:'Note cleanup'}).selectOption('off')
 await page.getByRole('button',{name:'Apply cleanup',exact:true}).click()
 await expect(page.getByTestId('cleanup-summary')).toHaveText(`0 notes hidden · ${piece.raw.notes.length} retained`,{timeout:30000})
 expect((await (await request.get('/api/pieces/cleanup-browser')).json()).raw).toEqual(piece.raw)
 expect(errors).toEqual([])
})
