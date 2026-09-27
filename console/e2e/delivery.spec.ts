import {test,expect} from '@playwright/test';
import {copyFile,unlink} from 'node:fs/promises';
test('no promotional slogans or false live-state text on the home screen',async({page})=>{await page.goto('/');const text=await page.locator('body').innerText();for(const unwanted of['Clarity creates leverage','Find signal','Build understanding','Sources before certainty','Evidence before action','All systems online','ONLINE | SECURE'])expect(text.toLowerCase()).not.toContain(unwanted.toLowerCase());});
test('record the real console interaction',async({browser})=>{
  const context=await browser.newContext({viewport:{width:1648,height:928},recordVideo:{dir:'evidence',size:{width:1648,height:928}}});const page=await context.newPage();await page.goto('http://127.0.0.1:4173');await expect(page.locator('canvas')).toHaveAttribute('data-render-frame',/\d+/);await page.waitForTimeout(1800);
  await page.getByRole('navigation').getByRole('button',{name:'Home',exact:true}).hover();await page.waitForTimeout(700);await page.mouse.move(1000,40);await page.waitForTimeout(500);
  const box=await page.locator('canvas').boundingBox();if(!box)throw new Error('Missing canvas');await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.60,box.y+box.height*.51,{steps:25});await page.mouse.up();await page.waitForTimeout(750);
  await page.getByRole('button',{name:'Explore projects',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:/Velvet Accademy/}).click();await expect(page.getByRole('complementary',{name:'Record inspector'})).toHaveCSS('opacity','1');await page.waitForTimeout(1400);await page.getByRole('button',{name:'Close record inspector'}).click();await page.waitForTimeout(650);
  const video=page.video();await context.close();if(!video)throw new Error('No recording');const source=await video.path();await copyFile(source,'evidence/ALFRED-Console-v02.webm');await unlink(source);
});
