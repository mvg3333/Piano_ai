import {OpenSheetMusicDisplay,TransposeCalculator} from 'opensheetmusicdisplay'

/** Render a separate, paginated score so viewport size and playback cannot affect printing. */
export async function printScore(musicxml:string,title:string,transpose:number){
 const preview=window.open('','_blank')
 if(!preview)throw new Error('Allow pop-ups for this app to open the printable score.')
 preview.document.title=title
 const style=preview.document.createElement('style')
 style.textContent=`@page{size:letter landscape;margin:0}*{box-sizing:border-box}body{margin:0;background:#eee;font-family:Arial,sans-serif}.tools{padding:16px;text-align:center}button{padding:10px 18px;cursor:pointer}.print-page{width:11in;height:8.5in;margin:16px auto;background:white;break-after:page;overflow:hidden}.print-page:last-child{break-after:auto}.print-page svg{display:block;width:100%;height:100%}@media print{body{background:white}.tools{display:none}.print-page{margin:0}}`
 preview.document.head.append(style)
 const toolbar=preview.document.createElement('div');toolbar.className='tools'
 toolbar.textContent='Preparing landscape score…'
 preview.document.body.append(toolbar)
 const host=document.createElement('div')
 host.style.cssText='position:fixed;left:-20000px;top:0;width:1056px;visibility:hidden'
 document.body.append(host)
 let display:OpenSheetMusicDisplay|undefined
 try{
  display=new OpenSheetMusicDisplay(host,{autoResize:false,backend:'svg',pageFormat:'Letter_L',disableCursor:true,drawTitle:true,drawSubtitle:false,drawComposer:false,drawPartNames:false,drawPartAbbreviations:false,drawMeasureNumbers:true})
  // Use the saved piece name, including any selected arrangement, as the printed title.
  const xml=new DOMParser().parseFromString(musicxml,'application/xml')
  if(xml.querySelector('parsererror'))throw new Error('The score could not be read for printing.')
  const root=xml.documentElement
  let movement=xml.querySelector('movement-title')
  if(!movement){movement=xml.createElement('movement-title');root.insertBefore(movement,root.firstChild)}
  movement.textContent=title
  xml.querySelectorAll('work-title').forEach(node=>{node.textContent=title})
  await display.load(new XMLSerializer().serializeToString(xml))
  if(preview.closed)return
  display.TransposeCalculator=new TransposeCalculator();display.Sheet.Transpose=transpose
  display.Zoom=1;display.render()
  const pages=host.querySelectorAll('svg')
  if(!pages.length)throw new Error('No printable score pages were generated.')
  for(const svg of pages){
   const page=preview.document.createElement('section');page.className='print-page'
   const copy=svg.cloneNode(true) as SVGSVGElement
   if(!copy.hasAttribute('viewBox'))copy.setAttribute('viewBox',`0 0 ${svg.width.baseVal.value} ${svg.height.baseVal.value}`)
   page.append(copy);preview.document.body.append(page)
  }
  toolbar.textContent='Landscape score ready. Choose “Save as PDF” or your printer. Use landscape and turn off browser headers and footers. '
  const button=preview.document.createElement('button');button.textContent='Print / Save PDF'
  button.onclick=()=>{preview.focus();preview.print()};toolbar.append(button)
  await preview.document.fonts.ready
  if(!preview.closed){preview.focus();preview.print()}
 }catch(error){
  if(!preview.closed)preview.close()
  throw error
 }finally{display?.clear();host.remove()}
}
