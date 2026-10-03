import {test,expect} from '@playwright/test';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync} from 'node:fs';
const output=process.env.ALFRED_CONSOLE_EVIDENCE??'evidence/refinement-09';
mkdirSync(output,{recursive:true});
test.beforeEach(async({page})=>{await page.mouse.move(1640,10);});
test('rail and favicon use the unchanged mark from the product deck',async({page})=>{
  expect(createHash('sha256').update(readFileSync('public/alfred-mark.jpg')).digest('hex')).toBe('a8594b3b4d9d8c78e3f70e8d99578638c4bdfc771093cf94e31f45344599d07d');
  await page.goto('/');const mark=page.locator('.rail-brand img');
  await expect(mark).toHaveAttribute('src','./alfred-mark.jpg');
  await expect.poll(()=>mark.evaluate(el=>(el as HTMLImageElement).naturalWidth)).toBe(344);
  expect(await mark.evaluate(el=>(el as HTMLImageElement).naturalHeight)).toBe(306);
  await expect(page.locator('link[rel=icon]')).toHaveAttribute('href','./alfred-mark.jpg');
});
test('switching Consciousness and Globe retains one renderer and real record browsing',async({page})=>{
  await page.goto('/');const canvas=page.locator('canvas');await expect(canvas).toHaveAttribute('data-render-frame',/\d+/);
  const id=await canvas.getAttribute('data-context-id');
  for(let i=0;i<4;i++){
    await page.getByRole('button',{name:'Consciousness',exact:true}).click();
    await expect(page.getByRole('button',{name:'Consciousness',exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(page.locator('.presence-label')).toHaveAttribute('data-activity','present');
    await expect(page.getByRole('button',{name:'Explore projects'})).toBeHidden();
    await page.getByRole('button',{name:'Globe',exact:true}).click();
    await expect(page.getByRole('button',{name:'Explore projects'})).toBeVisible();
    await expect(canvas).toHaveAttribute('data-context-id',id!);expect(await page.locator('canvas').count()).toBe(1);
  }
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();
  await page.getByRole('button',{name:'Browse',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/}).click();
  await expect(page.getByRole('complementary',{name:'Record inspector'}).getByText('design-01')).toBeVisible();
  await page.getByRole('button',{name:'Close record inspector'}).click();
  await expect(page.getByRole('complementary',{name:'Record inspector'})).toHaveCount(0);
});
test('typing gathers the supplied silhouette, then pause freezes its pixels',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Consciousness',exact:true}).click();
  const canvas=page.locator('canvas');await expect(canvas).toHaveAttribute('data-presence-particles','980');
  await page.waitForTimeout(1700);const idle=await canvas.screenshot();
  await page.waitForTimeout(450);expect(idle.equals(await canvas.screenshot())).toBe(false);
  await page.getByLabel('Command or search').fill('What needs my attention?');
  await expect(page.locator('.presence-label')).toHaveAttribute('data-activity','typing');
  await page.waitForTimeout(1700);expect(idle.equals(await canvas.screenshot())).toBe(false);
  await page.screenshot({path:output+'/consciousness-typing.png'});
  await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.waitForTimeout(350);
  const a=await canvas.screenshot();await page.waitForTimeout(450);expect(a.equals(await canvas.screenshot())).toBe(true);
  await page.getByRole('button',{name:'Resume sphere motion',exact:true}).click();
  await page.getByLabel('Command or search').fill('');await page.getByLabel('Command or search').blur();
  await expect(page.locator('.presence-label')).toHaveAttribute('data-activity','present');
});
test('reduced motion is a stationary exact silhouette and still supports search',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();await page.waitForTimeout(600);
  const canvas=page.locator('canvas'),a=await canvas.screenshot();await page.waitForTimeout(400);expect(a.equals(await canvas.screenshot())).toBe(true);
  expect(await page.locator('.surface-particle').count()).toBe(0);
  await page.keyboard.press('Control+k');await page.getByLabel('Search records').fill('Velvet');
  await expect(page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/})).toBeVisible();
});
test('rotating the globe cannot tilt the brand silhouette in Consciousness',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/');
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();const canvas=page.locator('canvas');
  await expect(canvas).toHaveAttribute('data-presence-particles','980');await page.waitForTimeout(300);const before=await canvas.screenshot();
  await page.getByRole('button',{name:'Globe',exact:true}).click();const box=await canvas.boundingBox();if(!box)throw Error('Missing canvas');
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.64,box.y+box.height*.55,{steps:10});await page.mouse.up();
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();await expect(canvas).toHaveAttribute('data-presence-particles','980');await page.waitForTimeout(300);
  expect(before.equals(await canvas.screenshot())).toBe(true);
});
test('surface flights are bounded, cancel on pause, and retain no removed content',async({page})=>{
  await page.goto('/');await page.getByRole('navigation').getByRole('button',{name:'Home',exact:true}).hover();
  await expect.poll(()=>page.locator('.surface-particle').count()).toBeGreaterThan(0);
  expect(await page.locator('.surface-particle').count()).toBeLessThanOrEqual(24);
  expect(await page.locator('.surface-motion').innerText()).toBe('');
  await page.mouse.move(1000,40);await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();
  await expect(page.locator('.surface-particle')).toHaveCount(0);
  await page.getByRole('button',{name:'Open executive briefing'}).click();await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.surface-particle')).toHaveCount(0);
});
test('offline Consciousness preview makes no HTTP or capture requests',async({page})=>{
  const requests:string[]=[],errors:string[]=[];
  page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>{throw Error('Unexpected microphone access');};});
  await page.setContent(readFileSync('ALFRED-Console.html','utf8'));
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();await page.getByLabel('Command or search').fill('Prepare my briefing');
  await expect(page.locator('.presence-label')).toHaveAttribute('data-activity','typing');
  await page.waitForTimeout(800);expect(requests).toEqual([]);expect(errors).toEqual([]);
});
test('mobile view tools remain reachable without horizontal overflow',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  // Navigation can reset Chromium's pointer over the rail. Move outside it
  // after the page loads, as the existing responsive acceptance checks do.
  await page.goto('/');await page.mouse.move(380,10);
  await expect(page.locator('.navigation-rail')).not.toHaveClass(/is-expanded/);
  await page.getByRole('button',{name:'Consciousness',exact:true}).click();
  await expect(page.getByRole('button',{name:'Browse',exact:true})).toBeInViewport();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Globe',exact:true}).click();await page.getByRole('button',{name:'Relationships',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Explicit relationships',exact:true})).toBeVisible();
});
