import {expect,test} from '@playwright/test';

test('sample Emergency108 pickup waits for Control Room authorization',async({page})=>{
  test.skip(process.env.GEOPULSE_TEST_EMERGENCY108!=='1','Requires the opt-in local integration profile');
  await page.goto('/');
  await page.getByLabel('Scenario for next run').selectOption('fleet-conflict-5x5');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await page.getByRole('button',{name:'Replay sample pickup'}).click();
  await expect(page.getByText('Awaiting police authorization')).toBeVisible();
  await expect(page.getByRole('button',{name:'Activate mission'})).toBeDisabled();
  const runId=await page.evaluate(()=>localStorage.getItem('geopulse.run'));
  const path=`/api/test-integrations/emergency108/runs/${runId}/handoffs/7001`;
  const pending=await (await page.request.get(path)).json();
  expect(pending.status).toBe('PENDING_AUTHORIZATION');
  expect(pending.simulated).toBe(true);
  await page.getByRole('button',{name:'Authorize hospital leg'}).click();
  await expect(page.getByText('Awaiting police authorization')).toHaveCount(0);
  await expect.poll(async()=>(await (await page.request.get(path)).json()).status).toBe('ACTIVE');
});
