import {test,expect} from '@playwright/test'
test('YouTube adapter uses supported rates, one clock and a visible player',async({page,request})=>{
 const piece=await (await request.get('/demo.json')).json()
 piece.source={kind:'youtube',videoId:'5U-WL0QvKCg'};piece.clipStart=5
 await page.route('**/demo.json',route=>route.fulfill({json:piece}))
 // Online startup restores the saved demo as well as loading its offline copy.
 await page.route('**/api/pieces/demo',route=>route.fulfill({json:piece}))
 await page.addInitScript(()=>{
  class Player {
   position=5;start=performance.now();speed=1;state=2;events:any
   constructor(element:HTMLElement,options:any){this.events=options.events;const iframe=document.createElement('iframe');iframe.title='Simulated YouTube player';iframe.style.cssText='width:100%;height:100%;border:0';element.replaceWith(iframe);setTimeout(()=>this.events.onReady(),0)}
   getCurrentTime(){return this.position+(this.state===1?(performance.now()-this.start)/1000*this.speed:0)}
   playVideo(){this.start=performance.now();this.state=1;this.events.onStateChange({data:1})}
   pauseVideo(){this.position=this.getCurrentTime();this.state=2;this.events.onStateChange({data:2})}
   seekTo(t:number){this.position=t;this.start=performance.now()}
   setPlaybackRate(r:number){this.position=this.getCurrentTime();this.start=performance.now();this.speed=r;this.events.onPlaybackRateChange()}
   getPlayerState(){return this.state}getAvailablePlaybackRates(){return [.5,1,2]}getPlaybackRate(){return this.speed}destroy(){}
  }
  ;(window as any).YT={Player}
 })
 await page.goto('/');await page.getByRole('button',{name:'Practice settings',exact:true}).filter({visible:true}).click()
 await page.getByRole('combobox',{name:'Settings playback source'}).selectOption('youtube')
 await page.getByRole('button',{name:'Close dialog'}).click()
 await expect(page.locator('iframe')).toBeVisible()
 expect(await page.getByRole('combobox',{name:'Playback speed'}).locator('option').allTextContents()).toEqual(['0.5×','1×','2×'])
 await page.getByRole('button',{name:'Play',exact:true}).click()
 await expect.poll(async()=>+(await page.getByRole('slider',{name:'Playback position'}).inputValue())).toBeGreaterThan(.5)
 await page.getByRole('button',{name:'Pause',exact:true}).click()
 await expect(page.getByRole('button',{name:'Both hands'})).toBeDisabled()
 for(const [width,height] of [[390,844],[844,390]]){
  await page.setViewportSize({width,height});await page.waitForTimeout(300)
  const video=await page.locator('iframe').boundingBox(),canvas=await page.locator('canvas').boundingBox(),transport=await page.locator('.transport').boundingBox()
  expect(video!.width).toBeGreaterThanOrEqual(200);expect(video!.height).toBeGreaterThanOrEqual(200)
  expect(canvas!.y+canvas!.height).toBeLessThanOrEqual(transport!.y+1)
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  await page.screenshot({path:`test-results/youtube-${width}x${height}.png`,fullPage:true})
 }
})
