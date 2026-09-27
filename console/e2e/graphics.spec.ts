import {test,expect} from '@playwright/test';
import {PerspectiveCamera,Vector3,Euler} from 'three';
import {fibonacciPoint} from '../src/scene/geometry';

test('a real mesh node opens its provenance record',async({page})=>{
 await page.goto('/');await expect(page.getByRole('button',{name:/WebGL2 renderer/})).toBeVisible();await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();
 const box=await page.locator('canvas').boundingBox();if(!box)throw new Error('Missing canvas');
 const p=new Vector3(...fibonacciPoint(0,10,1.023)).applyEuler(new Euler(.12,-.15,.10));const camera=new PerspectiveCamera(33,box.width/box.height,.1,30);camera.position.z=4.5;camera.updateMatrixWorld();p.project(camera);
 await page.mouse.click(box.x+(p.x+1)*box.width/2,box.y+(1-p.y)*box.height/2);
 await expect(page.getByRole('complementary',{name:'Record inspector'}).getByRole('heading',{name:'Velvet Accademy',exact:true})).toBeVisible();
});

test('pause freezes the rendered field and resume changes it',async({page})=>{
 await page.goto('/');await expect(page.getByRole('button',{name:/WebGL2 renderer/})).toBeVisible();await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.waitForTimeout(500);
 const canvas=page.locator('canvas'),a=await canvas.screenshot();await page.waitForTimeout(600);const b=await canvas.screenshot();expect(a.equals(b)).toBe(true);
 await page.getByRole('button',{name:'Resume sphere motion',exact:true}).click();await page.waitForTimeout(1000);const c=await canvas.screenshot();expect(b.equals(c)).toBe(false);
});

test('drag rotates the actual camera while the ambient motion is paused',async({page})=>{
 await page.goto('/');await expect(page.getByRole('button',{name:/WebGL2 renderer/})).toBeVisible();await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();await page.waitForTimeout(200);
 const canvas=page.locator('canvas'),box=await canvas.boundingBox();if(!box)throw new Error('Missing canvas');const before=await canvas.screenshot();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.55,{steps:12});await page.mouse.up();await page.waitForTimeout(500);
 const after=await canvas.screenshot();expect(before.equals(after)).toBe(false);await page.screenshot({path:'evidence/rotated-sphere.png'});
});

test('desktop footer and graph labels are not clipped',async({page})=>{
 await page.goto('/');const footer=await page.locator('.operations-footer').boundingBox();if(!footer)throw new Error('Missing footer');expect(footer.y+footer.height).toBeLessThanOrEqual(928);
 const work=await page.locator('.workspace').boundingBox();if(!work)throw new Error('Missing workspace');for(const item of await page.locator('.category-label').all()){const box=await item.boundingBox();if(!box)throw new Error('Missing category label');expect(box.x).toBeGreaterThanOrEqual(work.x);expect(box.x+box.width).toBeLessThanOrEqual(work.x+work.width);}
});
