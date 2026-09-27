import {test,expect} from '@playwright/test';

// Separate from luminance sampling: verify the real hit area while the field moves.
test('rail geometry follows hover and keyboard state without a stale overlay',async({page})=>{
  await page.mouse.move(1600,10);
  await page.goto('/');
  await expect.poll(async()=>Number(await page.locator('canvas').getAttribute('data-render-frame')),{timeout:30000}).toBeGreaterThan(2);
  const canvas=page.locator('canvas'),context=await canvas.getAttribute('data-context-id');
  const before=await canvas.boundingBox();
  await page.getByRole('navigation').getByRole('button',{name:'Home',exact:true}).hover();
  await expect(page.locator('.rail-surface')).toHaveCSS('width','248px',{timeout:10000});
  await page.mouse.move(1000,40);
  await page.getByRole('button',{name:'Search workspace',exact:true}).focus();
  await expect(page.locator('.navigation-rail')).not.toHaveClass(/is-expanded/);
  await expect(page.locator('.rail-surface')).toHaveCSS('width','78px',{timeout:10000});
  expect(await canvas.boundingBox()).toEqual(before);
  await expect(canvas).toHaveAttribute('data-context-id',context!);
});
