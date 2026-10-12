import {test,expect} from '@playwright/test'

test('practice panel expands, restores and accepts a custom height',async({page})=>{
 await page.goto('/')
 const stage=page.locator('.practice-stage')
 await expect(page.getByRole('heading',{name:'Windowlight'})).toBeVisible()
 const original=(await stage.boundingBox())!.height
 await page.getByRole('button',{name:'Expand practice',exact:true}).click()
 await expect(page.locator('.piece-heading')).toBeHidden()
 await expect(page.locator('.arrangement-bar')).toBeHidden()
 await expect.poll(async()=>(await stage.boundingBox())!.height).toBeGreaterThan(original)
 const expanded=await stage.boundingBox(),transport=await page.locator('.transport').boundingBox()
 expect(expanded!.y+expanded!.height).toBeLessThanOrEqual(transport!.y)
 await page.getByRole('button',{name:'Restore size',exact:true}).click()
 await page.getByRole('slider',{name:'Practice panel height',exact:true}).fill('900')
 await expect.poll(async()=>(await stage.boundingBox())!.height).toBe(900)
 await page.getByRole('button',{name:'Auto fit',exact:true}).click()
 await expect.poll(async()=>(await stage.boundingBox())!.height).toBeCloseTo(original,0)
})
