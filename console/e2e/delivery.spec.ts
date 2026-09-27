import {test,expect} from '@playwright/test';
import {copyFile,unlink} from 'node:fs/promises';

test('settled record inspector is opaque and readable',async({page})=>{
 await page.goto('/');await expect(page.getByRole('button',{name:/WebGL2 renderer/})).toBeVisible();
 await page.getByRole('button',{name:'Pause sphere motion',exact:true}).click();
 await page.getByRole('button',{name:'Search workspace',exact:true}).click();
 await page.getByLabel('Search records').fill('Velvet');
 await page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/}).click();
 const inspector=page.getByRole('complementary',{name:'Record inspector'});
 await expect(inspector).toHaveCSS('opacity','1');
 await expect(inspector.getByRole('heading',{name:'Provenance',exact:true})).toBeVisible();
 await page.screenshot({path:'evidence/inspector-settled.png'});
});

test('mobile command and shortcuts remain above the fixed navigation',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 const bar=await page.locator('.command-bar').boundingBox(),rail=await page.locator('.command-shortcuts').boundingBox(),nav=await page.locator('.navigation nav').boundingBox();
 if(!bar||!nav||!rail)throw new Error('Missing mobile control');
 expect(bar.y+bar.height).toBeLessThan(nav.y);expect(rail.y+rail.height).toBeLessThan(nav.y);
 await page.getByLabel('Command or search').fill('/brief');await page.getByRole('button',{name:'Run local command'}).click();
 await expect(page.getByRole('heading',{name:'Your briefing',exact:true})).toBeVisible();
});

test('record a short demonstration of the real rendering and inspector',async({browser})=>{
 const context=await browser.newContext({viewport:{width:1648,height:928},recordVideo:{dir:'evidence',size:{width:1280,height:720}}});
 const page=await context.newPage();await page.goto('http://127.0.0.1:4173');
 await expect(page.getByRole('button',{name:/WebGL2 renderer/})).toBeVisible();await page.waitForTimeout(2500);
 const box=await page.locator('canvas').boundingBox();if(!box)throw new Error('Missing sphere');
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.6,box.y+box.height*.5,{steps:24});await page.mouse.up();await page.waitForTimeout(1200);
 await page.getByRole('button',{name:'Explore projects',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/}).click();
 await expect(page.getByRole('complementary',{name:'Record inspector'})).toHaveCSS('opacity','1');await page.waitForTimeout(1800);
 await page.getByRole('button',{name:'Close record inspector'}).click();await page.waitForTimeout(1000);
 const video=page.video();await context.close();if(!video)throw new Error('Missing video capture');
 const source=await video.path();await copyFile(source,'evidence/ALFRED-Console-Demo.webm');await unlink(source);
});
