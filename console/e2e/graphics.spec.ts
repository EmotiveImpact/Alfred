import {test,expect} from '@playwright/test';
import {PerspectiveCamera,Vector3} from 'three';
import {writeFileSync} from 'node:fs';
import {recordPosition} from '../src/domain/projection';
import {createDemoSnapshot} from '../src/domain/fixtures';
import {luminance} from './png';
test('a real record mesh opens the right provenance',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.getByRole('button',{name:'Reset graph view'}).click();await page.waitForTimeout(300);
  const box=await page.locator('canvas').boundingBox();if(!box)throw new Error('No canvas');
  const camera=new PerspectiveCamera(34,box.width/box.height,.1,30);camera.position.z=Math.max(4,3.2/(box.width/box.height));camera.updateMatrixWorld();
  const p=new Vector3(...recordPosition(createDemoSnapshot().records[0])).project(camera);await page.mouse.click(box.x+(p.x+1)*box.width/2,box.y+(1-p.y)*box.height/2);
  await expect(page.getByRole('complementary',{name:'Record inspector'}).getByRole('heading',{name:'Velvet Accademy',exact:true})).toBeVisible();
});
test('paused pixels remain identical; resume changes the field',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.mouse.move(1150,40);await page.waitForTimeout(500);
  const canvas=page.locator('canvas'),a=await canvas.screenshot();await page.waitForTimeout(500);const b=await canvas.screenshot();expect(a.equals(b)).toBe(true);
  await page.getByRole('button',{name:'Resume sphere motion',exact:true}).click();await page.waitForTimeout(800);const c=await canvas.screenshot();expect(b.equals(c)).toBe(false);
});
test('drag rotates a paused view',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.waitForTimeout(200);
  const canvas=page.locator('canvas'),box=await canvas.boundingBox();if(!box)throw new Error('No canvas');const a=await canvas.screenshot();
  await page.mouse.move(box.x+box.width*.50,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.66,box.y+box.height*.5,{steps:15});await page.mouse.up();await page.mouse.move(1150,40);await page.waitForTimeout(500);expect(a.equals(await canvas.screenshot())).toBe(false);
});
test('animated frames have no large exposure or black-frame jumps in this capture',async({page})=>{
  test.setTimeout(180000);
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);await page.waitForTimeout(700);await page.mouse.move(1150,40);
  const box=await page.locator('canvas').boundingBox();if(!box)throw new Error('No canvas');
  const samples:number[]=[];for(let i=0;i<12;i++){samples.push(luminance(await page.screenshot({clip:box})));await page.waitForTimeout(90);}
  const max=Math.max(...samples),min=Math.min(...samples),ratios=samples.slice(1).map((x,i)=>Math.abs(x-samples[i])/Math.max(samples[i],.01));
  writeFileSync('evidence/temporal-luminance.json',JSON.stringify({samples,minimum:min,maximum:max,maxAdjacentRelativeChange:Math.max(...ratios),scope:'Twelve software-Chromium screenshot samples; not a physical-display flicker certification.'},null,2));
  expect(min).toBeGreaterThan(.2);expect(min/max).toBeGreaterThan(.7);expect(Math.max(...ratios)).toBeLessThan(.2);
});
test('ordinary UI state changes preserve the renderer',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);const id=await page.locator('canvas').getAttribute('data-context-id');
  await page.getByRole('checkbox',{name:/Review the console direction/}).click();await page.getByRole('button',{name:'Open executive briefing'}).click();await page.getByRole('button',{name:'Close panel'}).click();
  await page.getByRole('button',{name:'Relationships',exact:true}).click();await page.screenshot({path:'evidence/relationships.png'});await expect(page.locator('canvas')).toHaveAttribute('data-context-id',id!);await page.getByRole('button',{name:'Field',exact:true}).click();await expect(page.locator('canvas')).toHaveAttribute('data-context-id',id!);
});
test('context loss is visible; record browsing remains available',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);
  await page.locator('canvas').evaluate(c=>(c as HTMLCanvasElement).getContext('webgl2')?.getExtension('WEBGL_lose_context')?.loseContext());
  await expect(page.getByText(/Graphics paused. Waiting for context recovery/)).toBeVisible();
  await page.getByRole('button',{name:'Browse',exact:true}).click();await expect(page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/})).toBeVisible();
});
test('context can recover and resume real rendering',async({page})=>{
  await page.goto('/');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);
  await page.locator('canvas').evaluate(c=>{const ext=(c as HTMLCanvasElement).getContext('webgl2')?.getExtension('WEBGL_lose_context');ext?.loseContext();setTimeout(()=>ext?.restoreContext(),400);});
  await expect(page.getByText(/Graphics paused. Waiting for context recovery/)).toBeVisible();await expect(page.getByText(/Graphics paused. Waiting for context recovery/)).toHaveCount(0);
  const a=await page.locator('canvas').getAttribute('data-render-frame');await page.waitForTimeout(500);const b=await page.locator('canvas').getAttribute('data-render-frame');expect(Number(b)).toBeGreaterThan(Number(a));expect(luminance(await page.locator('canvas').screenshot())).toBeGreaterThan(.2);
});
