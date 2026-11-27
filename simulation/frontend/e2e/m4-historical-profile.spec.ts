import {test,expect} from '@playwright/test';

test('calibrated scenario shows the selected route’s projected historical interval', async ({page})=>{
  await page.goto('/welcome');
  await page.getByRole('radio',{name:/Predictable corridor congestion/}).check();
  await page.getByRole('link',{name:'Open Police Control Room'}).click();
  await expect(page.getByLabel('Scenario for next run')).toHaveValue('predictable-congestion-5x5');
  await page.getByLabel('Live information horizon').selectOption('2');
  await page.getByRole('button',{name:'Create run',exact:true}).click();
  await page.getByRole('button',{name:'Activate mission'}).click();
  await page.getByRole('button',{name:'Ambulance Routing',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Why this turn?'})).toBeVisible();
  await expect(page.getByText(/Decision 1 at .*2-hop window/)).toBeVisible();
  const road=page.getByLabel('Inspect road estimate');
  await road.selectOption('n00_02_n01_02');
  await expect(page.getByText(/historical · available · [\d.]+s · Historical interval (20–40|40–60)s/)).toBeVisible();
  await road.selectOption('n00_00_n00_01');
  await expect(page.getByText(/live · available · [\d.]+s/)).toBeVisible();
});
