// Render the generated local report. Requires Playwright and installed Chrome.
const {chromium} = require('playwright');
const path = require('path');
const {pathToFileURL} = require('url');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const page = await browser.newPage({viewport:{width:1360,height:1000}});
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.resolve('outputs/partie-3/radar.html')).href);
  await page.waitForFunction(()=>document.querySelectorAll('.js-plotly-plot .main-svg').length >= 2);
  const traces=await page.evaluate(()=>['macro-series','baseline-series'].map(id=>document.getElementById(id).data.length));
  if(traces.join(',')!=='2,4') throw new Error('Missing plot traces');
  await page.screenshot({path:'outputs/partie-3/preview.png',fullPage:true});
  await page.locator('#baseline-series .legendtoggle').first().click();
  await page.waitForFunction(()=>document.getElementById('baseline-series').data[0].visible==='legendonly');
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('#macro-series .main-svg').getBoundingClientRect().width<400);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
  await page.screenshot({path:'outputs/partie-3/preview-mobile.png',fullPage:true});
  await browser.close();
  if(errors.length || overflow) throw new Error(JSON.stringify({errors,overflow}));
  console.log(JSON.stringify({charts:2,traces,legendInteraction:'passed',mobileOverflow:false,pageErrors:errors}));
})().catch(e=>{console.error(e);process.exit(1)});
