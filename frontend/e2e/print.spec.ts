import {test,expect} from '@playwright/test'

test('print preview contains the complete landscape score without playback UI',async({page,context})=>{
 await context.addInitScript(()=>{window.print=()=>{document.body.dataset.printRequested='true'}})
 await page.goto('/')
 await expect(page.locator('.score-render svg').first()).toBeVisible({timeout:20000})
 const popupEvent=page.waitForEvent('popup')
 await page.getByRole('button',{name:'Print / Save PDF',exact:true}).click()
 const popup=await popupEvent
 await expect(popup.locator('body')).toHaveAttribute('data-print-requested','true',{timeout:20000})
 const pages=popup.locator('.print-page')
 await expect(pages).toHaveCount(3)
 for(const sheet of await pages.all()){
  const box=await sheet.boundingBox()
  expect(box!.width/box!.height).toBeCloseTo(11/8.5,2)
  await expect(sheet.locator('svg')).toBeVisible()
 }
 await expect(popup.locator('.transport,.active-score-note,[id^=cursor]')).toHaveCount(0)
 await expect(popup).toHaveTitle('Windowlight')
 await popup.screenshot({path:'test-results/print-landscape.png',fullPage:true})
 await popup.emulateMedia({media:'print'})
 await expect(popup.locator('.tools')).toBeHidden()
 await popup.close()
 await expect(page.getByRole('button',{name:'Print / Save PDF',exact:true})).toBeEnabled()
})
